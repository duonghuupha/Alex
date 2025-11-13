import cv2
import face_recognition
import os
import speech_recognition as sr
import pyttsx3

# Khởi tạo giọng nói
engine = pyttsx3.init()
engine.setProperty('rate', 150)
engine.setProperty('voice', 'HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\TTS_VIE_1')  # Nếu có giọng Việt

def speak(text):
    engine.say(text)
    engine.runAndWait()

def capture_face(name):
    cam = cv2.VideoCapture(0)
    while True:
        ret, frame = cam.read()
        cv2.imshow("Nhấn 's' để lưu khuôn mặt", frame)
        if cv2.waitKey(1) & 0xFF == ord('s'):
            cv2.imwrite(f"faces/{name}.jpg", frame)
            speak(f"Đã lưu khuôn mặt của {name}")
            break
    cam.release()
    cv2.destroyAllWindows()

def recognize_face():
    known_encodings = []
    known_names = []

    for file in os.listdir("faces"):
        img = face_recognition.load_image_file(f"faces/{file}")
        enc = face_recognition.face_encodings(img)[0]
        known_encodings.append(enc)
        known_names.append(file.split(".")[0])

    cam = cv2.VideoCapture(0)
    while True:
        ret, frame = cam.read()
        rgb = frame[:, :, ::-1]
        faces = face_recognition.face_locations(rgb)
        encodings = face_recognition.face_encodings(rgb, faces)

        for enc in encodings:
            matches = face_recognition.compare_faces(known_encodings, enc)
            if True in matches:
                name = known_names[matches.index(True)]
                speak(f"Xin chào {name}, rất vui được gặp lại bạn!")
                cam.release()
                cv2.destroyAllWindows()
                return name

        cv2.imshow("Nhấn 'q' để thoát", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()

def listen_and_reply():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        speak("Tôi đang lắng nghe bạn...")
        audio = r.listen(source)

    try:
        text = r.recognize_google(audio, language="vi-VN")
        speak(f"Bạn vừa nói: {text}")
    except:
        speak("Xin lỗi, tôi không nghe rõ.")

# Chạy chương trình
if not os.listdir("faces"):
    speak("Chưa có dữ liệu khuôn mặt. Vui lòng nhập tên để lưu.")
    name = input("Nhập tên bạn: ")
    capture_face(name)
else:
    recognize_face()

listen_and_reply()