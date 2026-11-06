import os
import warnings

# Suppress Pygame Welcome Message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"

# Suppress PyTorch & Hugging Face Warnings
warnings.filterwarnings("ignore")
os.environ['PYTHONWARNINGS'] = "ignore"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

import requests

# ================= CLOUD MEMORY (JSONBIN) CONFIGURATION =================
JSONBIN_BIN_ID = ""
JSONBIN_API_KEY = ""

def fetch_cloud_memory():
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
    headers = {"X-Master-Key": JSONBIN_API_KEY}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("record", {})
    except Exception as e:
        print("Memory Fetch Error:", e)
    return {}

def save_cloud_memory(memory_data):
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
    headers = {
        "Content-Type": "application/json",
        "X-Master-Key": JSONBIN_API_KEY
    }
    try:
        requests.put(url, json=memory_data, headers=headers)
    except Exception as e:
        print("Memory Save Error:", e)

import re
import sys
import time
import shutil
import urllib.parse
import urllib.request
import webbrowser
import threading
import speech_recognition as sr
from groq import Groq
import pyautogui
import psutil
import sounddevice as sd
import smtplib
from email.mime.text import MIMEText
from kokoro import KPipeline
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from flask import Flask, request, jsonify

# ================= IMPORT CONFIG & API KEYS =================
from config import (
    GROQ_API_KEY, 
    GEMINI_API_KEY, 
    TELEGRAM_BOT_TOKEN, 
    TELEGRAM_API_ID, 
    TELEGRAM_API_HASH, 
    CONNECTED_DEVICES,
    CC_USER,
    CC_PASS
)

# Initialize Gemini Client cleanly using config key
from google import genai
try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception:
    gemini_client = None

print("Loaded Config successfully for Neo.")

def call_gemini_chat(prompt):
    """Gemini API call handler"""
    try:
        if not gemini_client:
            return "Gemini client not initialized."
        response = gemini_client.models.generate_content(
            model='gemini-3.8-flash',  # <--- Yahan model name update kar diya hai
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"[Gemini API Error]: {e}")
        return None

    
import pytesseract
tesseract_possible_paths = [
    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    r'C:\Users\Samitto\tessdoc\tesseract.exe',
    os.path.expanduser(r'~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe')
]
for path in tesseract_possible_paths:
    if os.path.exists(path):
        pytesseract.pytesseract.tesseract_cmd = path
        break

# Telegram Personal Account Library
try:
    from pyrogram import Client
    PYROGRAM_AVAILABLE = True
except ImportError:
    PYROGRAM_AVAILABLE = False
    Client = None

# DuckDuckGo Search
try:
    from duckduckgo_search import DDGS
    DDG_AVAILABLE = True
except ImportError:
    DDG_AVAILABLE = False

# Local RAG Memory (ChromaDB)
try:
    import chromadb
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False

from sfx import play_sound
from gui_core import NeoVisualizer
import hand_studio  
from PIL import Image

# ================= GROQ CLOUD AI CONFIGURATION =================
groq_client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "openai/gpt-oss-20b"

def _groq_stream(messages):
    try:
        completion = groq_client.chat.completions.create(
            model=GROQ_MODEL, messages=messages, stream=True
        )
        for chunk in completion:
            delta = chunk.choices[0].delta.content
            if delta:
                yield {"message": {"content": delta}}
    except Exception as e:
        print(f"[Groq API Error]: {e}")
        yield {"message": {"content": "ERROR"}}

def call_groq_chat(messages, stream=True):
    """stream=True -> generator of chunks; stream=False -> single dict."""
    if stream:
        return _groq_stream(messages)
    try:
        completion = groq_client.chat.completions.create(
            model=GROQ_MODEL, messages=messages, stream=False
        )
        return {"message": {"content": completion.choices[0].message.content}}
    except Exception as e:
        print(f"[Groq API Error]: {e}")
        return {"message": {"content": "ERROR"}}

is_playing_music = False
original_volume = 1.0
recording_active = False
latest_camera_frame = None
camera_stop_event = threading.Event()
camera_thread = None
camera_running = False

# ================= CONTACTS CONFIG =================
SENDER_EMAIL = ""    # apni EMail yaha pr likhe    
SENDER_APP_PASSWORD = ""   # Sender app password yahan daale          

CONTACTS = {
    "maa": {"phone": "+91978", "email": "rahul@gmail.com", "insta": "rahul_official", "telegram": "+91978"},
    "papa": {"phone": "+91978", "email": "prajapatssstp14@gmail.com", "insta": "friend_handle", "telegram": "+91"},
    
}

if PYROGRAM_AVAILABLE:
    tg_client = Client("neo_personal_session", api_id=TELEGRAM_API_ID, api_hash=TELEGRAM_API_HASH)
else:
    tg_client = None

app = Flask(__name__)
viz = NeoVisualizer()

class NeoMemoryManager:
    def __init__(self):
        self.enabled = MEMORY_AVAILABLE
        if self.enabled:
            try:
                self.client = chromadb.PersistentClient(path="./neo_memory_db")
                self.collection = self.client.get_or_create_collection("user_memory")
            except Exception as e:
                print(f"[Memory Init Error]: {e}")
                self.enabled = False

    def save_memory(self, text):
        if not self.enabled or not text.strip():
            return
        try:
            mem_id = f"mem_{int(time.time()*1000)}"
            self.collection.add(documents=[text], ids=[mem_id])
            print(f"[Memory Saved]: {text}")
        except Exception as e:
            print(f"[Memory Save Error]: {e}")

    def query_memory(self, query):
        if not self.enabled:
            return ""
        try:
            results = self.collection.query(query_texts=[query], n_results=2)
            docs = results.get("documents", [[]])[0]
            return " ".join(docs)
        except Exception:
            return ""

neo_memory = NeoMemoryManager()

print("Loading Kokoro-82M Voice Engine...")
try:
    tts_pipeline = KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M')
    KOKORO_AVAILABLE = True
except Exception as e:
    print(f"Kokoro initialization error: {e}")
    KOKORO_AVAILABLE = False

play_sound("startup")
print("NEO v6.0 Dual Cloud Engine (Groq + Gemini) Online!")

APP_COMMANDS = {
    "code": ("code.exe", "code"),
    "vs code": ("code.exe", "code"),
    "vscode": ("code.exe", "code"),
    "chrome": ("chrome.exe", "chrome"),
    "browser": ("chrome.exe", "chrome"),
    "notepad": ("notepad.exe", "notepad"),
    "calculator": ("calc.exe", "calc"),
    "cmd": ("cmd.exe", "cmd"),
    "terminal": ("cmd.exe", "cmd"),
    "task manager": ("Taskmgr.exe", "taskmgr")
}

def get_master_volume():
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        return volume.GetMasterVolumeLevelScalar()
    except Exception:
        return 0.8

def set_master_volume(level):
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level, None)
    except Exception:
        pass

def lower_volume_50_percent():
    global original_volume
    original_volume = get_master_volume()
    set_master_volume(max(0.05, original_volume * 0.4))

def restore_volume():
    global original_volume
    set_master_volume(original_volume)

tts_lock = threading.Lock()

def speak_sentence(sentence_text):
    if not KOKORO_AVAILABLE or not sentence_text.strip():
        return
    with tts_lock:   # ek time par ek hi awaaz (CC thread + mic thread safe)
        try:
            viz.set_state("SPEAKING")
            generator = tts_pipeline(sentence_text, voice='af_heart', speed=1.1)
            for _, _, audio in generator:
                amplitude = float(abs(audio).max()) if len(audio) > 0 else 0.5
                viz.set_amplitude(amplitude)
                sd.play(audio, 24000)
                sd.wait()
        except Exception as e:
            print(f"TTS Error: {e}")
        finally:
            viz.set_amplitude(0.2)
            viz.set_state("IDLE")

def speak_and_stream(groq_stream):
    print("\n[Neo]: ", end="", flush=True)
    sentence_buffer = ""

    for chunk in groq_stream:
        token = chunk['message']['content']
        if token == "ERROR":
            return False
        sys.stdout.write(token)
        sys.stdout.flush()
        sentence_buffer += token

        if any(punct in token for punct in ['.', '!', '?', '\n']):
            clean_sentence = sentence_buffer.strip()
            if clean_sentence:
                speak_sentence(clean_sentence)
            sentence_buffer = ""

    if sentence_buffer.strip():
        speak_sentence(sentence_buffer.strip())
    print("\n")
    viz.set_state("IDLE")
    return True

def speak(text):
    print(f"\n[Neo]: {text}\n")
    speak_sentence(text)

from cc_agent import CCAgent

def _cc_llm(prompt):
    txt = call_gemini_chat(prompt)
    if txt:
        return txt
    parts = []
    for ch in call_groq_chat([{"role": "user", "content": prompt}], stream=True):
        t = ch["message"]["content"]
        if t == "ERROR":
            return None
        parts.append(t)
    return "".join(parts)

cc_agent = CCAgent(
    CC_USER, CC_PASS, llm=_cc_llm, speak=speak,
    on_answer=lambda q, a: neo_memory.save_memory(f"CC Q: {q} | A: {a[:300]}"),
)    

def take_screenshot():
    try:
        os.makedirs("screenshots", exist_ok=True)
        path = os.path.join("screenshots", f"screenshot_{int(time.time())}.png")
        pyautogui.screenshot().save(path)
        speak("Screenshot captured and saved successfully, Samitto.")
    except Exception as e:
        print(f"Screenshot Error: {e}")
        speak("Failed to capture screenshot.")

def record_screen_background():
    global recording_active
    import numpy as np
    import cv2
    recording_active = True
    speak("Screen recording started.")
    try:
        os.makedirs("recordings", exist_ok=True)
        path = os.path.join("recordings", f"recording_{int(time.time())}.avi")
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        screen_size = pyautogui.size()
        out = cv2.VideoWriter(path, fourcc, 15.0, screen_size)
        while recording_active:
            img = pyautogui.screenshot()
            frame = np.array(img)
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            out.write(frame)
            time.sleep(0.05)
        out.release()
        speak("Screen recording saved successfully.")
    except Exception as e:
        print(f"Recording Error: {e}")
        speak("Screen recording stopped due to an error.")

def stop_screen_recording():
    global recording_active
    if recording_active:
        recording_active = False
    else:
        speak("No active screen recording found.")

def click_camera_snapshot():
    global latest_camera_frame
    import cv2
    if latest_camera_frame is not None:
        try:
            os.makedirs("cam_photos", exist_ok=True)
            path = os.path.join("cam_photos", f"cam_photo_{int(time.time())}.png")
            cv2.imwrite(path, latest_camera_frame)
            speak("Camera photo captured and saved!")
        except Exception as e:
            print(f"Cam Photo Error: {e}")
            speak("Failed to save camera photo.")
    else:
        speak("Camera is not active right now.")

def run_hand_tracking_camera():
    global latest_camera_frame, camera_running
    camera_running = True
    camera_stop_event.clear()

    def _remember_frame(frame):
        global latest_camera_frame
        latest_camera_frame = frame

    try:
        hand_studio.run_blocking(speak=speak, stop_event=camera_stop_event, on_frame=_remember_frame)
    except Exception as e:
        print(f"[NEO Hand Studio Error]: {e}")
        speak("The camera module encountered an error.")
    finally:
        camera_stop_event.set()
        latest_camera_frame = None
        camera_running = False
        print("[NEO] Camera closed. Assistant remains active.")

def stop_hand_tracking_camera():
    if camera_running:
        camera_stop_event.set()
        speak("Camera closed. NEO is still running.")
    else:
        speak("Camera is already closed.")

def send_whatsapp_msg(target_name, message):
    try:
        contact_info = CONTACTS.get(target_name.lower(), {})
        phone_no = contact_info.get("phone", target_name)
        clean_number = "".join([c for c in phone_no if c.isdigit()])
        if len(clean_number) == 10:
            clean_number = "91" + clean_number
        speak_sentence(f"Opening WhatsApp for {target_name}")
        encoded_msg = urllib.parse.quote(message)
        os.system(f'start "" "whatsapp://send?phone={clean_number}&text={encoded_msg}"')
        time.sleep(4)
        pyautogui.press('enter')
        speak("WhatsApp message dispatched!")
    except Exception:
        speak("Failed to send WhatsApp message.")

def send_email(target_name, subject, body):
    try:
        contact_info = CONTACTS.get(target_name.lower(), {})
        recipient_email = contact_info.get("email", target_name)
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        speak_sentence(f"Sending email to {target_name}")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        speak("Email sent successfully!")
    except Exception:
        speak("Failed to send email.")

def send_telegram_msg(target_name, message):
    try:
        contact_info = CONTACTS.get(target_name.lower(), {})
        chat_id = contact_info.get("telegram", target_name)
        
        speak_sentence(f"Sending Telegram message to {target_name}")
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message
        }
        response = requests.post(url, json=payload, timeout=5)
        
        if response.status_code == 200:
            speak("Telegram message delivered successfully!")
        else:
            print(f"[Telegram API Error]: {response.text}")
            speak("Failed to deliver Telegram message.")
    except Exception as e:
        print(f"[Telegram Error]: {e}")
        speak("Failed to send Telegram message.")

def send_instagram_msg(target_name, message):
    try:
        contact_info = CONTACTS.get(target_name.lower(), {})
        insta_username = contact_info.get("insta", target_name)
        speak_sentence(f"Opening Instagram chat for {target_name}")
        webbrowser.open(f"https://www.instagram.com/direct/t/{insta_username}/")
        time.sleep(6)
        pyautogui.write(message)
        pyautogui.press('enter')
        speak("Instagram message dispatched!")
    except Exception:
        speak("Failed to send Instagram message.")

def play_youtube_video(song_name):
    try:
        search_keyword = urllib.parse.quote(song_name)
        search_url = f"https://www.youtube.com/results?search_query={search_keyword}"
        req = urllib.request.Request(search_url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req)
        video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
        if video_ids:
            webbrowser.open(f"https://www.youtube.com/watch?v={video_ids[0]}")
        else:
            webbrowser.open(search_url)
    except Exception:
        webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote(song_name)}")

def get_system_status():
    battery = psutil.sensors_battery()
    cpu_usage = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    status_msg = f"CPU usage is at {cpu_usage} percent. RAM usage is at {ram.percent} percent."
    if battery:
        plugged = "plugged in" if battery.power_plugged else "on battery"
        status_msg += f" Battery is at {battery.percent} percent and {plugged}."
    return status_msg

def get_live_weather(location=""):
    try:
        city = location if location else "Jodhpur"
        url = f"https://wttr.in/{city}?format=%C+%t"
        response = requests.get(url, timeout=4)
        if response.status_code == 200:
            return f"The current weather in {city} is {response.text.strip()}."
    except Exception:
        pass
    return "Sorry Samitto, I couldn't fetch the weather right now."

def activate_coding_mode():
    speak("Activating Coding Mode, Samitto.")
    os.system("start code")
    time.sleep(2)
    play_youtube_video("Lofi hip hop radio beats to relax study to")

def activate_gaming_mode():
    speak("Gaming Mode activated.")

def organize_downloads_folder():
    try:
        downloads_path = os.path.expanduser("~\\Downloads")
        if not os.path.exists(downloads_path):
            speak("Downloads folder not found.")
            return
        folders = {
            "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
            "Documents": [".pdf", ".docx", ".txt", ".pptx", ".xlsx"],
            "Scripts": [".py", ".js", ".cpp", ".java", ".sh"],
            "Archives": [".zip", ".rar", ".7z", ".tar"],
            "Executables": [".exe", ".msi"]
        }
        for folder_name in folders.keys():
            os.makedirs(os.path.join(downloads_path, folder_name), exist_ok=True)

        for filename in os.listdir(downloads_path):
            file_path = os.path.join(downloads_path, filename)
            if os.path.isfile(file_path):
                ext = os.path.splitext(filename)[1].lower()
                for folder_name, extensions in folders.items():
                    if ext in extensions:
                        shutil.move(file_path, os.path.join(downloads_path, folder_name, filename))
                        break
        speak("Your downloads folder has been organized!")
    except Exception:
        speak("Failed to organize files.")

def set_reminder(delay_seconds, reminder_text):
    def _timer():
        time.sleep(delay_seconds)
        speak(f"Reminder alert Samitto: {reminder_text}")
    threading.Thread(target=_timer, daemon=True).start()

def evaluate_companion_mood(command):
    romantic_keywords = ["love", "pyar", "cute", "beautiful", "sundar", "sharma", "blush", "date", "jaan", "babe", "sweet"]
    if any(kw in command.lower() for kw in romantic_keywords):
        viz.set_state("BLUSHING")
    else:
        viz.set_state("THINKING")

def listen_audio_once():
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 500 if is_playing_music else 300
    recognizer.dynamic_energy_threshold = True

    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.2)
        try:
            viz.set_state("LISTENING")
            play_sound("listening")
            audio = recognizer.listen(source, timeout=3, phrase_time_limit=5)
            text = recognizer.recognize_google(audio).lower()
            return text
        except Exception:
            return ""
        finally:
            if viz.state == "LISTENING":
                viz.set_state("IDLE")

def close_application(command):
    for app_name, (process_name, _) in APP_COMMANDS.items():
        if app_name in command:
            os.system(f"taskkill /f /im {process_name}")
            speak(f"Closed {app_name}.")
            return True
    pyautogui.hotkey('alt', 'f4')
    speak("Closing current window.")
    return True

def process_command(raw_text):
    global is_playing_music

    command = raw_text.lower()
    command = re.sub(r"\b(hey neo|turn on neo|neo|neow|nio)\b", " ", command)
    command = re.sub(r"\s+", " ", command).strip()

    if not command:
        return

    camera_exit_phrases = ["exit camera", "close camera", "stop camera", "quit camera", "camera off",
                           "camera exit", "camera close", "camera stop", "camera band", "band camera",
                           "turn off camera", "close the camera", "camera hatao", "camera bandh"]
    if any(phrase in command for phrase in camera_exit_phrases) or \
            (camera_running and command in ("exit", "quit", "close", "band karo", "band kar do")):
        stop_hand_tracking_camera()
        return

    if camera_running and hand_studio.handle_voice(command):
        return

    if re.search(r"\b(cc|c c|see see|curiosity coach)\b", command):
        if any(k in command for k in ["stop", "band", "exit"]):
            if cc_agent.running:
                cc_agent.stop()
                speak("Curiosity Coach session band kar raha hoon.")
            else:
                speak("Curiosity Coach session abhi chal nahi raha.")
            return
        if any(k in command for k in ["ask", "question", "puch"]):
            mins = 60
            m = re.search(r"(\d+)\s*(hour|ghant|hr)", command)
            if m: mins = int(m.group(1)) * 60
            m = re.search(r"(\d+)\s*min", command)
            if m: mins = int(m.group(1))
            cc_agent.start(duration_min=mins)
            return

    print(f"\n==> EXECUTING ACTION: '{command}'")
    evaluate_companion_mood(command)

    if "shutdown" in command or "exit" in command or "bye" in command:
        speak_sentence("Shutting down. Goodbye Samitto!")
        cc_agent.stop()
        camera_stop_event.set()
        viz.set_state("IDLE")
        play_sound("shutdown")
        viz.running = False
        sys.exit()

    elif any(k in command for k in ["screenshot", "screen shot", "capture screen"]):
        take_screenshot()

    elif any(k in command for k in ["screen record", "start recording", "record screen"]):
        if not recording_active:
            threading.Thread(target=record_screen_background, daemon=True).start()
        else:
            speak("Screen recording is already running.")

    elif any(k in command for k in ["stop recording", "stop screen record"]):
        stop_screen_recording()

    elif any(k in command for k in ["click photo", "capture photo", "photo click", "take picture"]):
        click_camera_snapshot()

    elif any(k in command for k in ["open camera", "track my fingers", "hand tracking", "camera"]):
        if camera_running:
            speak("Camera is already active.")
        else:
            speak_sentence("Launching NEO Gesture Studio...")
            threading.Thread(target=run_hand_tracking_camera, daemon=True).start()

    elif "coding mode" in command:
        activate_coding_mode()

    elif "gaming mode" in command:
        activate_gaming_mode()

    elif "organize" in command or "sort files" in command:
        speak_sentence("Organizing your downloads folder...")
        organize_downloads_folder()

    elif "remind me" in command:
        speak("I have set a reminder timer for you.")
        set_reminder(60, command)

    elif "remember" in command or "note down" in command:
        note = command.replace("remember", "").replace("note down", "").strip()
        neo_memory.save_memory(note)
        speak("Stored in my local memory database.")

    elif "recall" in command or "what do you remember" in command:
        query = command.replace("recall", "").replace("what do you remember about", "").strip()
        recalled = neo_memory.query_memory(query)
        if recalled:
            speak(f"Found in memory: {recalled}")
        else:
            speak("I couldn't find any relevant memory records.")

    elif "whatsapp" in command:
        parts = command.replace("send whatsapp to", "").replace("whatsapp", "").strip()
        target, msg = (parts.split("saying", 1) if "saying" in parts else (parts, "Hello from Neo Assistant!"))
        send_whatsapp_msg(target.strip(), msg.strip())

    elif "email" in command or "mail" in command:
        parts = command.replace("send email to", "").replace("send mail to", "").replace("email", "").replace("mail", "").strip()
        target, msg = (parts.split("saying", 1) if "saying" in parts else (parts, "Important update from Neo Assistant"))
        send_email(target.strip(), "Update from Neo", msg.strip())

    elif "telegram" in command or "tele" in command:
        parts = command.replace("send telegram to", "").replace("send tele to", "").replace("telegram", "").replace("tele", "").strip()
        target, msg = (parts.split("saying", 1) if "saying" in parts else (parts, "Hello from Neo!"))
        send_telegram_msg(target.strip(), msg.strip())

    elif "instagram" in command or "insta" in command:
        parts = command.replace("send instagram to", "").replace("send insta to", "").replace("instagram", "").replace("insta", "").strip()
        target, msg = (parts.split("saying", 1) if "saying" in parts else (parts, "Hey there!"))
        send_instagram_msg(target.strip(), msg.strip())

    elif any(k in command for k in ["save file", "save this", "save document"]):
        pyautogui.hotkey('ctrl', 's')
        speak("File saved.")

    elif "close" in command or "band karo" in command:
        close_application(command)

    elif any(k in command for k in ["battery", "system status", "cpu", "ram", "health"]):
        status = get_system_status()
        speak(status)

    elif any(k in command for k in ["skip ad", "skip ads", "ad skip", "skip advertisement"]):
        speak_sentence("Skipping ad now!")
        pyautogui.press('tab')
        time.sleep(0.1)
        pyautogui.press('tab')
        time.sleep(0.1)
        pyautogui.press('tab')
        time.sleep(0.1)
        pyautogui.press('tab')
        time.sleep(0.1)
        pyautogui.press('enter') 

    elif any(k in command for k in ["lock pc", "lock system", "lock my laptop"]):
        speak_sentence("Locking system, Samitto.")
        import ctypes
        ctypes.windll.user32.LockWorkStation()

    elif any(k in command for k in ["play music", "pause music", "stop music", "resume"]):
        speak_sentence("Toggling media playback.")
        pyautogui.press('playpause')       

    elif "open" in command:
        app_found = False
        for app_name, (_, exec_cmd) in APP_COMMANDS.items():
            if app_name in command:
                speak(f"Opening {app_name}.")
                os.system(f"start {exec_cmd}")
                app_found = True
                break
        if not app_found:
            target = command.replace("open", "").strip()
            speak(f"Opening {target}.")
            webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(target)}")

    elif "pause" in command or "stop music" in command:
        pyautogui.press('playpause')
        is_playing_music = False
        speak("Paused media.")
        restore_volume()

    elif "play" in command:
        song = command.replace("play", "").strip()
        if song:
            speak_sentence(f"Playing {song} on YouTube")
            play_youtube_video(song)
            is_playing_music = True
        else:
            speak_sentence("What song would you like me to play, Samitto?")
            viz.set_state("IDLE")
            return

    elif any(k in command for k in ["weather", "mausam", "temperature"]):
        city_search = re.sub(r"\b(weather|mausam|temperature|in|ka|ki|kaisa|hai)\b", " ", command).strip()
        weather_info = get_live_weather(city_search)
        speak(weather_info)

    elif command.startswith("gemini") or "ask gemini" in command:
        prompt_text = command.replace("gemini", "").replace("ask gemini", "").strip()
        speak_sentence("Asking Gemini...")
        response = call_gemini_chat(prompt_text)
        if response:
            speak(response[:300])
        else:
            speak("Gemini service had an issue.")

    else:
        try:
            if is_playing_music:
                lower_volume_50_percent()
            
            past_context = neo_memory.query_memory(command)
            sys_prompt = "You are Neo, an advanced and affectionate AI companion to Samitto. Keep responses warm, natural, and under 2 sentences."
            if past_context:
                sys_prompt += f" Memory Context: {past_context}"

            stream = call_groq_chat(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": command}
                ],
                stream=True
            )
            success = speak_and_stream(stream)

            if not success:
                gemini_res = call_gemini_chat(f"{sys_prompt}\nUser: {command}")
                if gemini_res:
                    speak(gemini_res)
                else:
                    speak("Both AI services are currently unresponsive.")

        except Exception as e:
            print(f"Primary AI Error: {e}")
            gemini_res = call_gemini_chat(command)
            if gemini_res:
                speak(gemini_res)
            else:
                speak("I had trouble connecting to cloud AI services.")
        finally:
            if is_playing_music:
                restore_volume()
            viz.set_state("IDLE")

# Flask Web Server
@app.route('/')
def home():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Neo Assistant</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { background: #0a0a12; color: #00f3ff; font-family: 'Segoe UI', sans-serif; text-align: center; padding: 15px; }
            h1 { font-size: 26px; text-shadow: 0 0 10px #00f3ff; margin-bottom: 15px; }
            .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 15px; }
            .stat-card { background: #121225; border: 1px solid #00f3ff44; padding: 10px; border-radius: 8px; font-size: 11px; }
            .stat-val { color: #fff; font-size: 13px; font-weight: bold; margin-top: 4px; }
            input { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: 1px solid #00f3ff; background: #121225; color: #fff; font-size: 15px; outline: none; }
            .btn { width: 100%; padding: 12px; margin: 5px 0; border: none; border-radius: 8px; font-weight: bold; font-size: 15px; cursor: pointer; }
            .btn-primary { background: #00f3ff; color: #000; }
            .btn-mic { background: #ff0055; color: white; }
            .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 8px; }
            .btn-ctrl { background: #1a1a36; border: 1px solid #00f3ff88; color: #fff; padding: 10px; border-radius: 8px; font-size: 14px; }
            #output { margin-top: 15px; color: #00f3ff; font-size: 13px; }
        </style>
    </head>
    <body>
        <h1>NEO CLOUD DUAL ENGINE</h1>
        <div class="stats-grid">
            <div class="stat-card">CPU<div id="cpu-stat" class="stat-val">--</div></div>
            <div class="stat-card">RAM<div id="ram-stat" class="stat-val">--</div></div>
            <div class="stat-card">BATTERY<div id="bat-stat" class="stat-val">--</div></div>
        </div>
        <input type="text" id="cmd" placeholder="Type command or 'Gemini ...'">
        <button class="btn btn-primary" onclick="sendCmd()">SEND COMMAND</button>
        <button class="btn btn-mic" onclick="startVoice()">🎤 SPEAK TO NEO</button>
        <div class="grid-3">
            <button class="btn-ctrl" onclick="mediaControl('voldown')">🔉 Vol -</button>
            <button class="btn-ctrl" onclick="mediaControl('playpause')">⏯️ Play/Pause</button>
            <button class="btn-ctrl" onclick="mediaControl('volup')">🔊 Vol +</button>
        </div>
        <div id="output">System Ready</div>
        <script>
            function fetchStats() {
                fetch('/system_stats')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('cpu-stat').innerText = data.cpu;
                    document.getElementById('ram-stat').innerText = data.ram;
                    document.getElementById('bat-stat').innerText = data.battery;
                }).catch(() => {});
            }
            setInterval(fetchStats, 3000);
            fetchStats();
            function sendCmd(text) {
                let inputElem = document.getElementById('cmd');
                let command = (typeof text === 'string' && text.length > 0) ? text : inputElem.value;
                command = command.trim();
                if(!command) return;
                document.getElementById('output').innerText = "Sending: " + command;
                fetch('/command', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({command: command})
                }).then(res => res.json()).then(data => {
                    document.getElementById('output').innerText = "Executed: " + command;
                    inputElem.value = '';
                });
            }
            function mediaControl(action) {
                fetch('/media_control', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({action: action})
                });
            }
            function startVoice() {
                let SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                if(!SpeechRecognition) return alert("Voice recognition not supported.");
                let recognition = new SpeechRecognition();
                document.getElementById('output').innerText = "Listening...";
                recognition.onresult = (e) => sendCmd(e.results[0][0].transcript);
                recognition.start();
            }
        </script>
    </body>
    </html>
    '''

@app.route('/command', methods=['POST'])
def api_command():
    data = request.get_json(force=True, silent=True) or {}
    user_cmd = data.get("command", "").strip()
    if not user_cmd:
        return jsonify({"error": "Empty command"}), 400
    threading.Thread(target=process_command, args=(user_cmd,), daemon=True).start()
    return jsonify({"status": "processing", "command": user_cmd})

@app.route('/media_control', methods=['POST'])
def api_media_control():
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action", "")
    if action == "playpause":
        pyautogui.press('playpause')
    elif action == "volup":
        pyautogui.press('volumeup')
    elif action == "voldown":
        pyautogui.press('volumedown')
    return jsonify({"status": "success", "action": action})

@app.route('/system_stats', methods=['GET'])
def api_system_stats():
    battery = psutil.sensors_battery()
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent
    bat_percent = f"{battery.percent}%" if battery else "N/A"
    plugged = "⚡" if (battery and battery.power_plugged) else "🔋"
    return jsonify({"cpu": f"{cpu}%", "ram": f"{ram}%", "battery": f"{bat_percent} {plugged}"})

def run_flask_server():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def microphone_listener_loop():
    WAKE_WORDS = ["neo", "neow", "nio", "play", "pause", "stop", "exit", "bye", "gemini", "open", "camera", "screenshot", "record", "photo", "cc", "see see", "curiosity"]
    while True:
        voice_text = listen_audio_once()
        if voice_text and (camera_running or any(w in voice_text for w in WAKE_WORDS)):
            process_command(voice_text)
        time.sleep(0.1)

def cli_listener_loop():
    while True:
        try:
            user_input = input("[You]: ").strip()
            if user_input:
                process_command(user_input)
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)

def main():
    print("==================================================")
    print("  Neo Assistant (Dual Engine Groq + Gemini Active) ")
    print("==================================================")
    speak("Dual cloud AI engine initialized. Ready Samitto.")

    threading.Thread(target=microphone_listener_loop, daemon=True).start()
    threading.Thread(target=cli_listener_loop, daemon=True).start()
    threading.Thread(target=run_flask_server, daemon=True).start()
    
    viz.run_loop()

if __name__ == "__main__":
    main()
