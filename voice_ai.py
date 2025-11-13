import speech_recognition as sr
import pyttsx3
import requests
import sqlite3
from transformers import AutoTokenizer, AutoModelForCausalLM
from config import GOOGLE_API_KEY, GOOGLE_CSE_ID

# Khởi tạo SQLite
conn = sqlite3.connect("database.db")
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    question TEXT,
    answer TEXT
)''')
conn.commit()

# Khởi tạo giọng nói
engine = pyttsx3.init()
engine.setProperty('rate', 150)

def speak(text):
    engine.say(text)
    engine.runAndWait()

# Nhận diện giọng nói
def listen():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        speak("Tôi đang lắng nghe bạn...")
        audio = r.listen(source)
    try:
        text = r.recognize_google(audio, language="vi-VN")
        return text
    except:
        speak("Xin lỗi, tôi không nghe rõ.")
        return ""

# Tìm kiếm Google
def search_google(query):
    url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_API_KEY}&cx={GOOGLE_CSE_ID}"
    res = requests.get(url).json()
    if "items" in res:
        return res["items"][0]["snippet"]
    elif "error" in res:
        print("Lỗi từ Google API:", res["error"]["message"])
        return "Không thể tìm thấy thông tin."
    else:
        return "Không có kết quả phù hợp."

# Phản hồi thông minh bằng PhoGPT
def get_ai_response(prompt):
    tokenizer = AutoTokenizer.from_pretrained("vinai/PhoGPT-4B-Chat", trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained("vinai/PhoGPT-4B-Chat", trust_remote_code=True)
    inputs = tokenizer(prompt, return_tensors="pt")
    outputs = model.generate(**inputs, max_new_tokens=100)
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

# Luồng xử lý chính
def run_voice_assistant(name="Người dùng"):
    question = listen()
    if question:
        web_info = search_google(question)
        prompt = f"Người dùng hỏi: {question}\nThông tin tìm kiếm: {web_info}\nHãy trả lời bằng tiếng Việt tự nhiên."
        answer = get_ai_response(prompt)
        speak(answer)
        print("Phản hồi:", answer)
        cursor.execute("INSERT INTO conversations (name, question, answer) VALUES (?, ?, ?)", (name, question, answer))
        conn.commit()

# Gọi thử
if __name__ == "__main__":
    run_voice_assistant()