"""
voice_chat_vi_final.py

GUI fullscreen giống mẫu bạn gửi, tích hợp:
- Giữ chức năng "học" (lưu hội thoại vào SQLite và lưu thông tin người khi nhận diện).
- Nếu có camera: tự động bật camera khi khởi động và hiển thị video ở giữa; avatar AI sẽ được đẩy lên góc phải trên.
- Nếu không có camera: avatar hiển thị ở giữa như giao diện mẫu.
- Khi phát hiện khuôn mặt mới: hỏi tên người (dialog) và lưu encoding để lần sau chào tự động.
- Tích hợp TTS (pyttsx3) để trả lời bằng giọng nói.

Yêu cầu cài đặt trước khi chạy (nếu muốn camera/nhận diện):
- pip install Pillow pyttsx3 sounddevice vosk opencv-python face_recognition numpy
  (face_recognition/dlib có thể cần thêm build tools; nếu không muốn, app vẫn chạy không camera)

Chạy: python voice_chat_vi_final.py
"""

import os
import queue
import threading
import json
import sqlite3
import time
import math
from difflib import SequenceMatcher
from tkinter import Tk, Label, Button, Text, END, Canvas, NW
from tkinter import simpledialog, messagebox
from PIL import Image, ImageTk, ImageFilter

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

# ========== CONFIG & DB ==========
DB_PATH = 'conversation.db'
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS conv (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, text TEXT, ts REAL)''')
cur.execute('''CREATE TABLE IF NOT EXISTS people (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, encoding BLOB)''')
cur.execute('''CREATE TABLE IF NOT EXISTS images (id INTEGER PRIMARY KEY AUTOINCREMENT, embedding BLOB, label TEXT)''')
conn.commit()

# helper functions
def save_message(role, text, connection=conn):
    c = connection.cursor()
    c.execute("INSERT INTO conv (role,text,ts) VALUES (?,?,?)", (role, text, time.time()))
    connection.commit()

# simple conversation reply (can be replaced with smarter model later)
def generate_reply(user_text):
    # save and simple echo fallback
    save_message('user', user_text)
    # here we could check DB for similar
    fallback = f"Mình nghe bạn nói: '{user_text}'. Bạn có thể nói thêm chi tiết được không?"
    save_message('assistant', fallback)
    return fallback

# TTS
def speak(text):
    save_message('assistant', text)
    if TTS_AVAILABLE:
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 150)
            engine.say(text)
            engine.runAndWait()
            return
        except Exception as e:
            print('TTS error:', e)
    print('Assistant (no TTS):', text)

# face DB utilities
import numpy as np

def load_known_faces():
    c = conn.cursor()
    c.execute('SELECT id,name,encoding FROM people')
    res = []
    for _id, name, enc_blob in c.fetchall():
        try:
            enc = np.frombuffer(enc_blob, dtype=np.float64)
            res.append((_id, name, enc))
        except Exception:
            continue
    return res

def save_new_face(name, encoding):
    c = conn.cursor()
    c.execute('INSERT INTO people (name, encoding) VALUES (?,?)', (name, encoding.tobytes()))
    conn.commit()

def find_matching_face(face_encoding, known, tolerance=0.6):
    best_name = None
    best_dist = None
    for _id, name, enc in known:
        d = np.linalg.norm(enc - face_encoding)
        if best_dist is None or d < best_dist:
            best_dist = d
            best_name = name
    if best_dist is not None and best_dist < tolerance:
        return best_name
    return None

# ========== GUI class ==========
class VoiceCameraApp:
    def __init__(self, root):
        self.root = root
        self.root.title('Trợ lý AI — Fullscreen')
        # fullscreen
        self.root.attributes('-fullscreen', True)
        self.width = self.root.winfo_screenwidth()
        self.height = self.root.winfo_screenheight()

        self.bg_color = '#fbfbfc'
        self.root.configure(bg=self.bg_color)

        # Canvas middle area for avatar / video
        self.canvas = Canvas(root, width=self.width, height=self.height, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)

        # Load avatar image (placeholder if not exists)
        here = os.path.dirname(__file__)
        avatar_path = os.path.join(here, 'person_avatar.png')
        if not os.path.exists(avatar_path):
            # create a simple placeholder
            im = Image.new('RGBA', (600, 600), (240, 240, 250))
            im = im.filter(ImageFilter.GaussianBlur(radius=0))
            im.save(avatar_path)
        self.avatar_orig = Image.open(avatar_path).convert('RGBA')

        # Precompute images for center and small corner
        self.avatar_center = ImageTk.PhotoImage(self.avatar_orig.resize((600, 600), Image.LANCZOS))
        self.avatar_corner = ImageTk.PhotoImage(self.avatar_orig.resize((180, 180), Image.LANCZOS))

        # initial state: no camera feed -> avatar center
        self.camera_active = False
        self.vid_frame = None
        self.known_faces = load_known_faces()

        # Draw center avatar
        self.center_image_id = self.canvas.create_image(self.width//2, self.height//2 - 40, image=self.avatar_center)

        # Status text under avatar
        self.status_text_id = self.canvas.create_text(self.width//2, self.height//2 + 320, text='Đang lắng nghe...', font=('Arial', 18), fill='#333')

        # small tip text red when no mic permission etc
        self.tip_text_id = self.canvas.create_text(self.width//2, self.height//2 + 360, text='', font=('Arial', 14), fill='red')

        # corner avatar (hidden initially)
        self.corner_image_id = self.canvas.create_image(self.width-120, 60, image=self.avatar_corner, state='hidden')

        # bottom-right label
        self.canvas.create_text(self.width-120, self.height-30, text='Trợ lý AI tiếng Việt', font=('Arial', 10), fill='#777')

        # Chat log (invisible by default, can be toggled) - small widget using Text in a window area
        self.chat_text = Text(root, width=60, height=8, font=('Arial', 12))
        self.chat_window = self.canvas.create_window(self.width//2, self.height-150, window=self.chat_text)
        self.chat_text.insert(END, 'Hệ thống sẵn sàng...\n')
        self.chat_text.config(state='disabled')

        # Start audio worker (simple inline interactive or STT integration later)
        self.start_audio_worker()

        # Try to start camera if available
        self.cap = None
        self.start_camera_if_available()

        # schedule periodic UI update for video frames
        self.update_ui()

        # bind Escape to exit fullscreen/quit
        self.root.bind('<Escape>', lambda e: self.quit())

    def start_audio_worker(self):
        # For now we just ensure assistant listens via console fallback or future STT
        # This can be replaced with vosk STT thread
        pass

    def start_camera_if_available(self):
        if not CV2_AVAILABLE:
            print('OpenCV not available -> camera disabled')
            return
        try:
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap or not cap.isOpened():
                cap.release()
                print('No camera found')
                return
            # camera ok
            self.cap = cap
            self.camera_active = True
            # move avatar to corner
            self.canvas.itemconfigure(self.center_image_id, state='hidden')
            self.canvas.itemconfigure(self.corner_image_id, state='normal')
            # update status
            self.canvas.itemconfigure(self.status_text_id, text='Camera hoạt động — Đang lắng nghe...')
            # start camera thread
            threading.Thread(target=self.camera_loop, daemon=True).start()
        except Exception as e:
            print('Camera start error:', e)

    def camera_loop(self):
        # camera read loop: detect faces and update chat log
        while self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.1)
                continue
            # convert to PIL image for display
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            # resize to fit a central area (70% screen width)
            max_w = int(self.width * 0.7)
            max_h = int(self.height * 0.7)
            img.thumbnail((max_w, max_h), Image.LANCZOS)
            self.vid_frame = ImageTk.PhotoImage(img)

            # face recognition on small frame for performance
            if FACE_AVAILABLE:
                small = cv2.resize(frame_rgb, (0,0), fx=0.25, fy=0.25)
                face_locs = face_recognition.face_locations(small)
                encs = face_recognition.face_encodings(small, face_locs)
                known = self.known_faces
                for enc in encs:
                    # scale encoding already computed; compare
                    name = find_matching_face(enc, known)
                    if name:
                        # known person: greet (on UI thread)
                        self.root.after(0, self.handle_known_person, name)
                    else:
                        # new person: ask name on UI thread
                        self.root.after(0, self.prompt_and_save_person, enc)
            time.sleep(0.03)

    def handle_known_person(self, name):
        text = f'Chào lại {name}!'
        self.append_chat('assistant', text)
        speak(text)

    def prompt_and_save_person(self, face_encoding):
        # Ask user for name via dialog - blocking dialog on UI thread
        name = simpledialog.askstring('Người mới', 'Phát hiện người mới. Nhập tên để lưu:')
        if name:
            # face_encoding from small frame; need to upcast to full precision
            enc = np.array(face_encoding, dtype=np.float64)
            try:
                save_new_face(name, enc)
                self.known_faces = load_known_faces()
                self.append_chat('assistant', f'Đã lưu thông tin {name}.')
                speak(f'Rất vui được gặp bạn {name}!')
            except Exception as e:
                messagebox.showerror('Lỗi', f'Không lưu được: {e}')

    def append_chat(self, role, text):
        self.chat_text.config(state='normal')
        self.chat_text.insert(END, f"{role.capitalize()}: {text}\n")
        self.chat_text.see(END)
        self.chat_text.config(state='disabled')

    def update_ui(self):
        # called in main thread periodically to update video or avatar
        if self.camera_active and self.vid_frame:
            # draw central video
            if hasattr(self, 'video_image_id'):
                self.canvas.itemconfigure(self.video_image_id, image=self.vid_frame)
            else:
                self.video_image_id = self.canvas.create_image(self.width//2, self.height//2 - 40, image=self.vid_frame)
            # ensure corner avatar shown
            self.canvas.itemconfigure(self.center_image_id, state='hidden')
            self.canvas.itemconfigure(self.corner_image_id, state='normal')
        else:
            # show center avatar
            self.canvas.itemconfigure(self.center_image_id, state='normal')
            self.canvas.itemconfigure(self.corner_image_id, state='hidden')
        # schedule next
        self.root.after(30, self.update_ui)

    def quit(self):
        try:
            if self.cap:
                self.cap.release()
        except Exception:
            pass
        self.root.destroy()

# ========== main ==========
def main():
    root = Tk()
    app = VoiceCameraApp(root)
    try:
        root.mainloop()
    finally:
        try:
            if app.cap:
                app.cap.release()
        except Exception:
            pass

if __name__ == '__main__':
    main()
