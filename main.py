import cv2
import threading
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import speech_recognition as sr
import pyttsx3
from gtts import gTTS
from playsound import playsound
import tempfile
import os
import time

# ==========================
# Nói tiếng Việt (ưu tiên giọng hệ thống, fallback gTTS)
# ==========================
def speak(text):
    try:
        engine.say(text)
        engine.runAndWait()
        print("🔊 Đã nói:", text)
    except Exception:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                tts = gTTS(text=text, lang="vi")
                tts.save(fp.name)
                print("🔊 (Google) Nói:", text)
                playsound(fp.name)
                os.remove(fp.name)
        except Exception as e:
            print("⚠️ Lỗi nói:", e)

# ==========================
# Khởi tạo giọng nói hệ thống
# ==========================
engine = pyttsx3.init()
voices = engine.getProperty('voices')
for v in voices:
    if "vi" in v.id.lower() or "viet" in v.name.lower() or "an" in v.name.lower():
        engine.setProperty('voice', v.id)
        break
engine.setProperty('rate', 170)

# ==========================
# Nhận giọng nói
# ==========================
recognizer = sr.Recognizer()

def listen_and_callback(callback):
    """Lắng nghe liên tục và gọi callback với nội dung nghe được"""
    while True:
        try:
            with sr.Microphone() as source:
                print("🎤 Đang lắng nghe...")
                recognizer.adjust_for_ambient_noise(source)
                audio = recognizer.listen(source, phrase_time_limit=6)
            text = recognizer.recognize_google(audio, language="vi-VN")
            print("🗣️ Bạn nói:", text)
            callback(text)
        except sr.UnknownValueError:
            pass
        except sr.RequestError as e:
            print("⚠️ Lỗi kết nối:", e)
        except Exception as e:
            print("❌ Lỗi khác:", e)
        time.sleep(0.3)

# ==========================
# Giao diện chính
# ==========================
class AlexApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Trợ lý ảo Alex")
        self.root.state("zoomed")
        self.root.configure(bg="#f2f2f2")

        self.frame = ttk.Frame(root)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # Avatar
        self.avatar_label = ttk.Label(self.frame)
        self.avatar_label.pack(pady=10)
        avatar_path = "avatar.png"
        if not os.path.exists(avatar_path):
            from PIL import ImageDraw
            img = Image.new("RGB", (200, 200), color="#90caf9")
            d = ImageDraw.Draw(img)
            d.text((60, 90), "A", fill="white")
            img.save(avatar_path)
        self.avatar_img = Image.open(avatar_path)
        self.avatar_img = self.avatar_img.resize((200, 200))
        self.avatar_photo = ImageTk.PhotoImage(self.avatar_img)
        self.avatar_label.config(image=self.avatar_photo)

        # Camera
        self.video_label = ttk.Label(self.frame)
        self.video_label.pack(pady=10)
        self.cap = cv2.VideoCapture(1)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
        self.update_camera()

        # Hộp log
        self.text_box = tk.Text(self.frame, height=10, font=("Segoe UI", 12))
        self.text_box.pack(fill=tk.BOTH, padx=10, pady=10, expand=True)

        # Luồng nghe
        self.listening_thread = threading.Thread(target=listen_and_callback, args=(self.on_voice_input,), daemon=True)
        self.listening_thread.start()

    def update_camera(self):
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            ratio = 640 / w
            frame = cv2.resize(frame, (640, int(h * ratio)))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.config(image=imgtk)
        self.root.after(30, self.update_camera)

    def on_voice_input(self, text):
        """Nhận phản hồi sau khi nghe"""
        self.text_box.insert(tk.END, f"👤 Bạn: {text}\n")
        self.text_box.see(tk.END)
        reply = self.generate_reply(text)
        self.text_box.insert(tk.END, f"🤖 Alex: {reply}\n\n")
        self.text_box.see(tk.END)
        threading.Thread(target=speak, args=(reply,), daemon=True).start()

    def generate_reply(self, text):
        t = text.lower()
        if "xin chào" in t or "chào" in t:
            return "Chào bạn, rất vui được gặp lại! Bạn cần mình giúp gì hôm nay?"
        elif "bạn tên gì" in t:
            return "Mình là Alex, trợ lý ảo của bạn."
        elif "mấy giờ" in t:
            return f"Bây giờ là {time.strftime('%H:%M')}."
        elif "camera" in t:
            return "Camera của bạn đang hoạt động rất tốt!"
        else:
            return "Mình chưa hiểu rõ lắm, bạn có thể nói lại không?"

# ==========================
# Khởi động
# ==========================
if __name__ == "__main__":
    root = tk.Tk()
    app = AlexApp(root)
    root.mainloop()
