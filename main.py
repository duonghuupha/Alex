# voice_camera_app.py
# Alex 2.0 — Fullscreen voice+camera assistant (Python 3.13 compatible)
# - GUI fullscreen, avatar dynamic (drawn), camera auto-start if available
# - face_recognition optional: ask name for new faces and greet on return
# - SQLite stores conversations and face encodings
# - TTS via pyttsx3, tries to select a VN male voice (young) if available

import os
import sys
import time
import threading
import queue
import sqlite3
import json
from math import sin, pi
from difflib import SequenceMatcher

# GUI
from tkinter import Tk, Canvas, Text, END, simpledialog, messagebox
from tkinter import NW
from PIL import Image, ImageTk, ImageDraw, ImageFilter

# Optional libs
try:
    import cv2
    CV2_AVAILABLE = True
except Exception:
    cv2 = None
    CV2_AVAILABLE = False

try:
    import face_recognition
    FACE_AVAILABLE = True
except Exception:
    face_recognition = None
    FACE_AVAILABLE = False

try:
    import pyttsx3
    TTS_AVAILABLE = True
except Exception:
    pyttsx3 = None
    TTS_AVAILABLE = False

try:
    import numpy as np
except Exception:
    np = None

# ========== DB setup ==========
DB_PATH = "voice_camera_data.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS conv (
    id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, text TEXT, ts REAL
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, encoding BLOB
)""")
conn.commit()

def save_message(role, text):
    cur = conn.cursor()
    cur.execute("INSERT INTO conv (role, text, ts) VALUES (?,?,?)", (role, text, time.time()))
    conn.commit()

# ========== TTS engine (reuse) ==========
_TTS_ENGINE = None

def select_vietnamese_male_engine(engine):
    # try to pick voice with Vietnamese locale or description; prefer male-ish voices
    try:
        voices = engine.getProperty("voices")
    except Exception:
        return None
    def is_vi(v):
        s = (str(getattr(v, "name", "")).lower() + " " + str(getattr(v, "id", "")).lower())
        return ("vietnam" in s) or ("vi_" in s) or ("vietnamese" in s) or ("vi-" in s) or ("tiếng việt" in s) or ("vi " in s)
    # 1) vi + male
    for v in voices:
        try:
            meta = (str(getattr(v, "name","")) + " " + str(getattr(v,"id",""))).lower()
            if is_vi(v) and ("male" in meta or "man" in meta or "m-" in meta):
                return v.id
        except Exception:
            continue
    # 2) vi any
    for v in voices:
        try:
            if is_vi(v):
                return v.id
        except Exception:
            continue
    # 3) male any
    for v in voices:
        try:
            meta = (str(getattr(v, "name","")) + " " + str(getattr(v,"id",""))).lower()
            if ("male" in meta or "man" in meta or "m-" in meta):
                return v.id
        except Exception:
            continue
    return None

def speak(text, block=True):
    """Speak text; reuse engine. block=True will run runAndWait() and block until done."""
    save_message('assistant', text)
    global _TTS_ENGINE
    if not TTS_AVAILABLE:
        print("TTS not available:", text)
        return
    try:
        if _TTS_ENGINE is None:
            _TTS_ENGINE = pyttsx3.init()
            vid = select_vietnamese_male_engine(_TTS_ENGINE)
            if vid:
                try:
                    _TTS_ENGINE.setProperty("voice", vid)
                except Exception:
                    pass
            try:
                _TTS_ENGINE.setProperty("rate", 150)
            except Exception:
                pass
        if block:
            _TTS_ENGINE.say(text)
            _TTS_ENGINE.runAndWait()
        else:
            # non-blocking: run in a dedicated thread to avoid UI blocking
            def _tb(t):
                try:
                    _TTS_ENGINE.say(t)
                    _TTS_ENGINE.runAndWait()
                except Exception as e:
                    print("TTS thread error:", e)
            threading.Thread(target=_tb, args=(text,), daemon=True).start()
    except Exception as e:
        print("TTS engine error:", e)
        print(text)

# ========== Face utilities ==========
def load_known_faces():
    cur = conn.cursor()
    cur.execute("SELECT id, name, encoding FROM people")
    rows = cur.fetchall()
    result = []
    for _id, name, enc_blob in rows:
        try:
            enc = np.frombuffer(enc_blob, dtype=np.float64)
            result.append((_id, name, enc))
        except Exception:
            continue
    return result

def save_new_face(name, encoding):
    cur = conn.cursor()
    cur.execute("INSERT INTO people (name, encoding) VALUES (?,?)", (name, encoding.tobytes()))
    conn.commit()

def find_match(encoding, known, tol=0.6):
    best = None
    best_d = None
    for _id, name, enc in known:
        d = np.linalg.norm(enc - encoding)
        if best_d is None or d < best_d:
            best_d = d
            best = name
    if best_d is not None and best_d < tol:
        return best
    return None

# ========== Avatar animation (drawn, no external file) ==========
def make_avatar_image(size=600, face_color=(64,130,255)):
    """Return PIL Image of a simple friendly male avatar (stylized)"""
    im = Image.new("RGBA", (size, size), (255,255,255,0))
    draw = ImageDraw.Draw(im)
    w = size
    # background circle
    draw.ellipse((0,0,w,w), fill=(240,248,255,255))
    # head
    cx = w//2; cy = w//2 - int(w*0.05)
    r = int(w*0.28)
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(245,220,200))
    # hair (simple shape)
    draw.polygon([(cx-r*0.8, cy-r*0.7),(cx+r*0.8, cy-r*0.9),(cx+r*0.3, cy-r*0.6),(cx-r*0.3, cy-r*0.6)], fill=(30,30,30))
    # eyes
    eye_w = int(r*0.25)
    draw.ellipse((cx-eye_w, cy-int(r*0.05), cx-eye_w//2, cy+eye_w//3), fill=(0,0,0))
    draw.ellipse((cx+eye_w//2, cy-int(r*0.05), cx+eye_w, cy+eye_w//3), fill=(0,0,0))
    # smile
    draw.arc((cx-int(r*0.6), cy+int(r*0.05), cx+int(r*0.6), cy+int(r*0.6)), start=200, end=340, fill=(150,30,30), width=6)
    # shirt
    draw.rectangle((cx-int(r*1.1), cy+int(r*0.6), cx+int(r*1.1), w), fill=(70,130,180))
    return im

# ========== App (Tkinter) ==========
class AssistantApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Alex — Trợ lý AI tiếng Việt")
        self.root.attributes("-fullscreen", True)
        self.w = self.root.winfo_screenwidth()
        self.h = self.root.winfo_screenheight()
        self.bg = "#f7fbff"
        self.root.configure(bg=self.bg)

        self.canvas = Canvas(root, width=self.w, height=self.h, bg=self.bg, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Create avatar base images
        self.avatar_pil = make_avatar_image(600)
        self.avatar_center = ImageTk.PhotoImage(self.avatar_pil.resize((500,500), Image.LANCZOS))
        self.avatar_small = ImageTk.PhotoImage(self.avatar_pil.resize((140,140), Image.LANCZOS))

        # dynamic ring parameters
        self.ring_phase = 0.0
        self.ring_id = None

        # initial center image
        self.center_id = self.canvas.create_image(self.w//2, self.h//2 - 70, image=self.avatar_center)
        # corner small (hidden initially)
        self.corner_id = self.canvas.create_image(self.w-100, 80, image=self.avatar_small, state="hidden")
        # status text
        self.status_id = self.canvas.create_text(self.w//2, self.h//2 + 300, text="Xin chào! Mình là Alex — Trợ lý tiếng Việt.", font=("Arial", 20), fill="#222")
        self.substatus_id = self.canvas.create_text(self.w//2, self.h//2 + 340, text="Đang lắng nghe...", font=("Arial", 16), fill="#444")
        # chat log (text widget placed as window)
        self.chat_text = Text(root, width=70, height=8, font=("Arial", 12))
        self.chat_text.insert(END, "Hệ thống sẵn sàng...\n")
        self.chat_text.config(state="disabled")
        self.chat_win = self.canvas.create_window(self.w//2, self.h-140, window=self.chat_text)

        # camera controls
        self.cap = None
        self.camera_active = False
        self.vid_photo = None

        # face knowledge
        self.known_faces = []
        if FACE_AVAILABLE and np is not None:
            self.known_faces = load_known_faces()

        # start audio worker (placeholder for STT integration)
        # start camera auto if available
        self.start_camera_auto()

        # animation loop
        self.animate()

        # exit on ESC
        self.root.bind("<Escape>", lambda e: self.quit())

    def append_chat(self, who, text):
        self.chat_text.config(state="normal")
        self.chat_text.insert(END, f"{who}: {text}\n")
        self.chat_text.see(END)
        self.chat_text.config(state="disabled")

    def start_camera_auto(self):
        if not CV2_AVAILABLE:
            print("OpenCV not available — camera disabled")
            self.append_chat("system", "Camera không khả dụng.")
            return
        try:
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap or not cap.isOpened():
                cap.release()
                self.append_chat("system", "Không tìm thấy camera.")
                return
            self.cap = cap
            self.camera_active = True
            # switch avatar to corner
            self.canvas.itemconfigure(self.center_id, state="hidden")
            self.canvas.itemconfigure(self.corner_id, state="normal")
            self.canvas.itemconfigure(self.status_id, text="Camera hoạt động")
            self.append_chat("system", "Camera bật — bắt đầu nhận diện.")
            # start camera thread
            threading.Thread(target=self.camera_loop, daemon=True).start()
        except Exception as e:
            print("Camera start error:", e)
            self.append_chat("system", f"Camera error: {e}")

    def camera_loop(self):
        while self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.05)
                continue
            # convert BGR -> RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # central display: scale to fit 70% width
            max_w = int(self.w * 0.7)
            max_h = int(self.h * 0.7)
            img = Image.fromarray(frame_rgb)
            img.thumbnail((max_w, max_h), Image.LANCZOS)
            self.vid_photo = ImageTk.PhotoImage(img)
            # face recognition on smaller frame for speed
            if FACE_AVAILABLE and np is not None:
                small = cv2.resize(frame_rgb, (0,0), fx=0.25, fy=0.25)
                face_locs = face_recognition.face_locations(small)
                encs = face_recognition.face_encodings(small, face_locs)
                for enc in encs:
                    # enc is for small frame scaling; still works for similarity
                    name = find_match(enc, self.known_faces) if self.known_faces else None
                    if name:
                        # greet once (use UI thread)
                        self.root.after(0, self.greet_person, name)
                    else:
                        # prompt for name once
                        self.root.after(0, self.prompt_save_person, enc)
            time.sleep(0.03)

    def greet_person(self, name):
        msg = f"Chào lại {name}!"
        self.append_chat("assistant", msg)
        speak(msg, block=False)
        # update status line
        self.canvas.itemconfigure(self.substatus_id, text=f"Chào mừng bạn trở lại, {name}!")

    def prompt_save_person(self, encoding):
        # ask name via dialog
        name = simpledialog.askstring("Người mới", "Phát hiện người mới. Mời nhập tên để lưu:")
        if not name:
            return
        try:
            enc = np.array(encoding, dtype=np.float64)
            save_new_face(name, enc)
            self.known_faces = load_known_faces()
            self.append_chat("system", f"Đã lưu {name}.")
            speak(f"Rất vui được gặp bạn {name}!", block=False)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không lưu được: {e}")

    def animate(self):
        # animate ring around center avatar if center visible
        self.ring_phase += 0.08
        # remove old ring then draw new (cheap approach)
        if self.ring_id:
            try:
                self.canvas.delete(self.ring_id)
            except Exception:
                pass
        # only draw ring when center avatar visible
        state = self.canvas.itemcget(self.center_id, "state")
        if state != "hidden":
            cx = self.w//2
            cy = self.h//2 - 70
            base_r = 320
            # dynamic radius oscillation
            r = base_r + 8 * sin(self.ring_phase)
            # ring coordinates
            x0 = cx - r; y0 = cy - r; x1 = cx + r; y1 = cy + r
            # draw translucent ring as image for nicer antialiasing
            ring_im = Image.new("RGBA", (int(r*2+10), int(r*2+10)), (255,255,255,0))
            draw = ImageDraw.Draw(ring_im)
            # gradient-ish ring:
            for i in range(10):
                alpha = int(20*(10-i))
                draw.ellipse((i, i, ring_im.size[0]-i, ring_im.size[1]-i), outline=(100,160,255,alpha))
            self.ring_tk = ImageTk.PhotoImage(ring_im)
            self.ring_id = self.canvas.create_image(cx - r -5, cy - r -5, image=self.ring_tk, anchor=NW)
        # update video image if available
        if self.camera_active and self.vid_photo:
            if hasattr(self, "video_id"):
                self.canvas.itemconfigure(self.video_id, image=self.vid_photo)
            else:
                self.video_id = self.canvas.create_image(self.w//2, self.h//2 - 70, image=self.vid_photo)
            # ensure corner avatar is visible
            self.canvas.itemconfigure(self.corner_id, state="normal")
        else:
            # ensure center avatar visible
            self.canvas.itemconfigure(self.center_id, state="normal")
            # hide video id if exists
            if hasattr(self, "video_id"):
                try:
                    self.canvas.delete(self.video_id)
                    delattr = False
                except Exception:
                    pass
        # schedule next draw
        self.root.after(30, self.animate)

    def quit(self):
        try:
            if self.cap:
                self.cap.release()
        except Exception:
            pass
        try:
            conn.commit()
            conn.close()
        except Exception:
            pass
        self.root.destroy()

# ========== Run ==========
def main():
    root = Tk()
    app = AssistantApp(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.quit()

if __name__ == "__main__":
    main()
