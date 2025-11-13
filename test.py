import requests
from config import GOOGLE_API_KEY, GOOGLE_CSE_ID

def search_google(query):
    url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_API_KEY}&cx={GOOGLE_CSE_ID}"
    res = requests.get(url).json()
    print(res["items"][0]["snippet"])

search_google("thời tiết Hà Nội hôm nay")