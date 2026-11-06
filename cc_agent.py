"""
cc_agent.py  --  NEO <-> Curiosity Coach automation (v2)

Install (ek baar):
    pip install playwright
    (system Chrome use hota hai; Chrome na ho to: playwright install chromium)

config.py me:
    CC_USER = "..."
    CC_PASS = "..."

v2 changes:
  * Login pehle VERIFY hota hai (password box gayab hona) - uske baad hi ask-coach khulta hai.
    (v1 ki galti: fields bharke turant dusre page par chala jata tha -> form reset.)
  * Typing React ke liye real keystrokes se hoti hai (fill() se React state update nahi hota).
  * Login button 3 tarike se dhundha jata hai: submit button -> text wala element -> Enter key.
  * Fail hone par screenshot + page ke inputs/buttons ki list cc_debug/ folder me save hoti hai.
"""
import json
import os
import random
import re
import threading
import time
from datetime import datetime

LOGIN_URL = "https://curiosity.swarnaayu.com/teacher-login"
ASK_URL = "https://curiosity.swarnaayu.com/ask-coach"

GRADES = [6, 7, 8, 9]
TOPICS = [
    "homework help",
    "class lesson explanation",
    "paper circuit",
    "ESE (environmental science / electronics activity)",
    "simple electric circuit",
    "series and parallel circuits",
    "STEM classroom experiment",
    "science exam preparation",
]

FALLBACK_QUESTIONS = [
    "How can I teach Class 6 students to make a simple paper circuit?",
    "Can you explain series and parallel circuits for Class 7 in an easy way?",
    "Give me 5 homework questions on conductors and insulators for Class 8.",
    "What is a good classroom demo of current and voltage for Class 9?",
    "What materials and steps do I need for a paper circuit activity?",
    "How do I explain an LED circuit to Class 8 students in a STEM lesson?",
]

LOGIN_BTN_RE = re.compile(r"^\s*(log\s?in|sign\s?in|submit|continue)\s*$", re.I)


class CCAgent:
    def __init__(self, user, password, llm, speak=print, on_answer=None,
                 headless=False, minimized=False, profile_dir="./cc_chrome_profile",
                 log_file="cc_log.jsonl"):
        """
        headless  : True = bilkul invisible (pehle False rakh ke test karo)
        minimized : True = window minimize hoke background me chalegi
        """
        self.user, self.password = user, password
        self.llm, self.speak, self.on_answer = llm, speak, on_answer
        self.headless, self.minimized = headless, minimized
        self.profile_dir, self.log_file = profile_dir, log_file
        self.stop_event = threading.Event()
        self.thread = None
        self.asked = []

    # ---------------- public API ----------------
    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, duration_min=60, gap_range=(90, 180)):
        if self.running:
            self.speak("Curiosity Coach session already running hai.")
            return
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run, args=(duration_min, gap_range), daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    # ---------------- question generation ----------------
    def _make_question(self, grade=None, label=None):
        topic = random.choice(TOPICS)
        if grade is None:
            grade = random.choice(GRADES)
        cls = label or f"Class {grade}"
        recent = "; ".join(self.asked[-8:]) or "none"
        prompt = (
            f"You are a STEM teacher. Write ONE short, specific question for an AI "
            f"teaching coach about: {cls} (grade {grade}), topic: {topic}. "
            f"Do not repeat these earlier questions: {recent}. "
            f"Return only the question text, no quotes, no numbering."
        )
        try:
            q = (self.llm(prompt) or "").strip().strip('"')
        except Exception:
            q = ""
        if not q or len(q) > 300:
            q = random.choice(FALLBACK_QUESTIONS)
        return q

    # ---------------- debugging ----------------
    def _debug_dump(self, page, tag):
        """Screenshot + inputs/buttons ki list -> cc_debug/. Isse selectors theek kiye ja sakte hain."""
        try:
            os.makedirs("cc_debug", exist_ok=True)
            ts = int(time.time())
            page.screenshot(path=f"cc_debug/{tag}_{ts}.png")
            info = page.evaluate("""() => ({
                url: location.href,
                inputs: [...document.querySelectorAll('input,textarea,[contenteditable=true]')]
                    .map(e => ({tag: e.tagName, type: e.type, name: e.name, id: e.id,
                                placeholder: e.placeholder, cls: String(e.className).slice(0, 80)})),
                buttons: [...document.querySelectorAll('button,[role=button],input[type=submit],a')]
                    .map(e => ({tag: e.tagName, text: (e.innerText || e.value || '').trim().slice(0, 40),
                                type: e.type || '', cls: String(e.className).slice(0, 80)})),
                alerts: [...document.querySelectorAll('[role=alert],.error,.alert,[class*=error i]')]
                    .map(e => e.innerText.trim().slice(0, 120))
            })""")
            with open(f"cc_debug/{tag}_{ts}.json", "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2, ensure_ascii=False)
            print(f"[CC] DEBUG saved cc_debug/{tag}_{ts}.png/.json")
            print(f"[CC] DEBUG page: {json.dumps(info, ensure_ascii=False)[:1500]}")
        except Exception as e:
            print(f"[CC] debug dump failed: {e}")

    # ---------------- login ----------------
    def _pw_visible(self, page):
        try:
            return page.locator("input[type='password']:visible").count() > 0
        except Exception:
            return False

    def _wait_logged_in(self, page, timeout=10):
        """Login tab maana jaye jab password box 2 lagatar checks me gayab ho."""
        t0, gone = time.time(), 0
        while time.time() - t0 < timeout:
            if not self._pw_visible(page):
                gone += 1
                if gone >= 2:
                    return True
            else:
                gone = 0
            time.sleep(0.5)
        return False

    def _type_into(self, box, text):
        """React ko real keystrokes chahiye; verify karke fill() fallback."""
        box.click()
        box.press("Control+A")
        box.press("Delete")
        box.press_sequentially(text, delay=35)
        try:
            if box.input_value() != text:      # contenteditable par input_value() error deta hai
                box.fill(text)
        except Exception:
            pass

    def _fill_credentials(self, page):
        pw = page.locator("input[type='password']:visible").first
        form = pw.locator("xpath=ancestor::form[1]")
        scope = form if form.count() else page
        user_box = scope.locator(
            "input:not([type='password']):not([type='hidden']):not([type='checkbox'])"
            ":not([type='radio']):not([type='submit']):not([type='button']):visible").first
        self._type_into(user_box, self.user)
        self._type_into(pw, self.password)
        return pw

    def _click_login(self, page, strategy):
        """3 alag tareeke; har ek True/False return karta hai (click hua ya nahi)."""
        try:
            if strategy == 1:
                loc = page.locator("button[type='submit']:visible, input[type='submit']:visible")
                if loc.count():
                    loc.first.click(timeout=3000)
                    return True
                loc = page.locator("button:visible, [role='button']:visible").filter(has_text=LOGIN_BTN_RE)
                if loc.count():
                    loc.last.click(timeout=3000)
                    return True
                return False
            if strategy == 2:
                loc = page.get_by_text(LOGIN_BTN_RE)
                if loc.count():
                    loc.last.click(timeout=3000)
                    return True
                return False
            page.locator("input[type='password']:visible").first.press("Enter")
            return True
        except Exception as e:
            print(f"[CC] click strategy {strategy} error: {e}")
            return False

    def _login(self, page):
        """True tabhi return karta hai jab login verify ho jaye."""
        for attempt in range(1, 4):
            print(f"[CC] Login attempt {attempt}/3")
            if attempt == 1 or "login" not in page.url.lower():
                page.goto(LOGIN_URL, wait_until="domcontentloaded")
            try:
                page.locator("input[type='password']:visible").first.wait_for(timeout=15000)
            except Exception:
                if "login" not in page.url.lower():
                    print("[CC] Pehle se logged in lag raha hai.")
                    return True
                self._debug_dump(page, "no_login_form")
                continue

            for strategy in (1, 2, 3):
                pw = self._fill_credentials(page)
                time.sleep(0.4)
                if not self._click_login(page, strategy):
                    continue
                if self._wait_logged_in(page, timeout=10):
                    time.sleep(2)   # token localStorage me save hone do
                    print(f"[CC] Login OK (strategy {strategy}) -> {page.url}")
                    return True
                alerts = page.locator("[role='alert'], .error, .alert").all_inner_texts()
                if alerts:
                    print(f"[CC] Site ne kaha: {alerts[:2]}")
            self._debug_dump(page, f"login_fail_{attempt}")
        return False

    # ---------------- class picker ----------------
    _JS_TAG_OLD = "document.querySelectorAll('*').forEach(e => e.setAttribute('data-cc-old', '1'))"

    # menu khulne ke baad jo NAYE visible elements aaye unme se class wale (6-9 digit) dhundo
    _JS_FIND_OPTIONS = """() => {
        const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
        const txt = e => (e.innerText || '').trim();
        const els = [...document.querySelectorAll('*:not([data-cc-old])')]
            .filter(e => vis(e) && txt(e).length > 0 && txt(e).length < 60);
        const re = /(^|[^\\d])([6-9])([^\\d]|$)/;
        let cand = els.filter(e => re.test(txt(e)));
        let withGrade = true;
        if (!cand.length) { cand = els; withGrade = false; }
        const leaf = cand.filter(e => !cand.some(o => o !== e && e.contains(o)));
        document.querySelectorAll('[data-cc-opt]').forEach(e => e.removeAttribute('data-cc-opt'));
        return leaf.map((e, i) => {
            e.setAttribute('data-cc-opt', String(i));
            const m = txt(e).match(re);
            return {i, text: txt(e).split('\\n')[0], grade: withGrade && m ? parseInt(m[2]) : null};
        });
    }"""

    def _class_button(self, page):
        btn = page.get_by_role("button", name=re.compile(r"pick a class", re.I))
        if btn.count():
            return btn.first
        return page.locator("button:visible").first      # sidebar ka sabse pehla button = class picker

    def _class_selected(self, page):
        try:
            return "pick a class" not in self._class_button(page).inner_text().lower()
        except Exception:
            return False

    def _choose_class(self, page):
        """Dropdown kholo, 6/7/8/9 me se ek class chuno. Return (grade, label)."""
        for attempt in range(2):
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            page.evaluate(self._JS_TAG_OLD)
            self._class_button(page).click(timeout=5000)
            time.sleep(0.8)
            opts = page.evaluate(self._JS_FIND_OPTIONS)
            if not opts:
                self._debug_dump(page, "class_menu_empty")
                continue
            wanted = [o for o in opts if o["grade"] in GRADES] or opts
            pick = random.choice(wanted)
            print(f"[CC] Class options: {[o['text'] for o in opts]} -> {pick['text']}")
            page.locator(f"[data-cc-opt='{pick['i']}']").first.click(timeout=5000)
            time.sleep(1.2)
            if self._class_selected(page):
                return pick["grade"], pick["text"]
            self._debug_dump(page, "class_not_selected")
        raise RuntimeError("Class select nahi ho payi - cc_debug/ ki JSON bhejo")

    # ---------------- chat ----------------
    def _find_input(self, page):
        text_like = ("input:visible:not([type='file']):not([type='hidden']):not([type='checkbox'])"
                     ":not([type='radio']):not([type='submit']):not([type='button']):not([type='password'])")
        for sel in ("input[placeholder*='Ask' i]:visible", "textarea:visible", text_like,
                    "[contenteditable='true']:visible"):
            loc = page.locator(sel).last
            try:
                loc.wait_for(state="visible", timeout=8000)
                return loc
            except Exception:
                continue
        self._debug_dump(page, "no_chat_input")
        raise RuntimeError("Chat input box nahi mila - cc_debug/ ki JSON file bhejo")

    def _body_text(self, page):
        try:
            return page.inner_text("body")
        except Exception:
            return ""

    def _open_ask_page(self, page):
        page.goto(ASK_URL, wait_until="domcontentloaded")
        time.sleep(2)
        if self._pw_visible(page):          # session expire -> redirect login
            if not self._login(page):
                raise RuntimeError("Login fail")
            page.goto(ASK_URL, wait_until="domcontentloaded")
            time.sleep(2)

    def _new_chat(self, page):
        """Chat lambi na ho jaye isliye har 10 sawal par New chat."""
        try:
            btn = page.get_by_role("button", name=re.compile(r"new chat", re.I))
            if btn.count():
                btn.first.click()
                time.sleep(1.5)
        except Exception:
            pass

    def _ask(self, page, question):
        before = self._body_text(page)
        box = self._find_input(page)
        self._type_into(box, question)
        box.press("Enter")
        time.sleep(1.2)
        if self._still_has_text(box, question):          # Enter se submit nahi hua
            row = box.locator("xpath=ancestor::*[.//button][1]")
            btns = row.locator("button:not([disabled])")
            if btns.count():
                btns.last.click()                        # row ka aakhri button = send icon
            else:
                self._debug_dump(page, "no_send_button")
                raise RuntimeError("Send button nahi mila")

        last_len, stable_since, t0 = len(before), time.time(), time.time()
        while time.time() - t0 < 120 and not self.stop_event.is_set():
            time.sleep(1)
            cur = len(self._body_text(page))
            if cur != last_len:
                last_len, stable_since = cur, time.time()
            elif cur > len(before) and time.time() - stable_since > 5:
                break
        after = self._body_text(page)
        ans = self._diff(before, after).replace(question, "").strip()
        if "pick a class first" in ans.lower():
            raise RuntimeError("Site ne kaha 'Pick a class first' - class select nahi thi")
        return ans[:1500]

    @staticmethod
    def _still_has_text(box, question):
        try:
            return question[:15] in box.input_value()
        except Exception:
            try:
                return question[:15] in box.inner_text()
            except Exception:
                return False

    @staticmethod
    def _diff(before, after):
        """Naya text nikalo: common prefix aur common suffix hata do (chat beech me add hoti hai)."""
        n = min(len(before), len(after))
        i = 0
        while i < n and before[i] == after[i]:
            i += 1
        j = 0
        while j < n - i and before[-1 - j] == after[-1 - j]:
            j += 1
        return after[i:len(after) - j].strip()

    def _log(self, question, answer):
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"),
                                "q": question, "a": answer}, ensure_ascii=False) + "\n")

    # ---------------- main loop ----------------
    def _launch(self, p):
        args = ["--start-minimized"] if (self.minimized and not self.headless) else []
        try:
            return p.chromium.launch_persistent_context(
                self.profile_dir, channel="chrome", headless=self.headless, args=args)
        except Exception as e:
            print(f"[CC] System Chrome nahi mila ({e}); bundled Chromium try kar raha hoon.")
            return p.chromium.launch_persistent_context(
                self.profile_dir, headless=self.headless, args=args)

    def _run(self, duration_min, gap_range):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[CC] playwright install nahi hai: pip install playwright")
            self.speak("Playwright install nahi hai. Terminal me pip install playwright chalao.")
            return

        end_time = time.time() + duration_min * 60
        count = 0
        try:
            with sync_playwright() as p:
                ctx = self._launch(p)
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                self.speak("Curiosity Coach me login kar raha hoon.")
                if not self._login(page):
                    self.speak("Login nahi ho paya. cc debug folder check karo.")
                    ctx.close()
                    return
                self._open_ask_page(page)
                self.speak(f"Login ho gaya. Main {duration_min} minute tak sawal puchunga.")

                fails = 0
                while time.time() < end_time and not self.stop_event.is_set():
                    q = ""
                    try:
                        grade, label = self._choose_class(page)
                        q = self._make_question(grade, label)
                        a = self._ask(page, q)
                        fails = 0
                    except Exception as e:
                        fails += 1
                        print(f"[CC] ask error ({fails}/3): {e}")
                        if fails >= 3:
                            self.speak("Sawal nahi bhej paa raha. Session band kar raha hoon.")
                            break
                        try:
                            self._open_ask_page(page)
                        except Exception as e2:
                            print(f"[CC] recover failed: {e2}")
                            break
                        continue
                    self.asked.append(q)
                    count += 1
                    print(f"[CC] Q{count}: {q}\n[CC] A: {a[:200]}...")
                    self._log(q, a)
                    if self.on_answer and a:
                        try:
                            self.on_answer(q, a)
                        except Exception:
                            pass
                    if count % 10 == 0:
                        self._new_chat(page)
                    self.stop_event.wait(random.randint(*gap_range))
                ctx.close()
        except Exception as e:
            print(f"[CC] Session error: {e}")
            self.speak("Curiosity Coach session me error aaya.")
            return
        self.speak(f"Curiosity Coach session khatam. Total {count} sawal puche.")
