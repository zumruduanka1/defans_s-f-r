from flask import Flask, request, jsonify, render_template
import requests, threading, time
import feedparser
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

feed = []
stats = {"total":0,"danger":0,"safe":0}

# -------- TEXT --------
def extract(url):
    try:
        r = requests.get(url, timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")
        return soup.get_text()[:1000]
    except:
        return ""

# -------- RISK --------
def risk(text):
    score = 10

    for k in ["şok","ifşa","iddia","gizli","son dakika"]:
        if k in text.lower():
            score += 15

    if "!" in text:
        score += 5

    return min(100, score)

# -------- RSS --------
def get_news():
    data = []
    try:
        d = feedparser.parse("https://news.google.com/rss?hl=tr&gl=TR&ceid=TR:tr")

        for e in d.entries[:10]:
            data.append({
                "text": e.title,
                "url": e.link
            })
    except:
        pass

    return data

# -------- WORKER --------
def worker():
    global feed, stats

    while True:
        items = get_news()

        # boş kalmasın
        if not items:
            items = [
                {"text":"Şok iddia sosyal medyada yayıldı"},
                {"text":"Gizli belge ortaya çıktı"},
                {"text":"Bu haber tartışılıyor"}
            ]

        new = []
        stats = {"total":0,"danger":0,"safe":0}

        for i in items:
            text = extract(i["url"]) if "url" in i else i["text"]

            if len(text) < 50:
                text = i["text"]

            r = risk(text)

            stats["total"] += 1

            if r >= 50:
                stats["danger"] += 1
            else:
                stats["safe"] += 1

            new.append({
                "text": i["text"][:100],
                "risk": r
            })

        feed = sorted(new, key=lambda x: x["risk"], reverse=True)

        time.sleep(15)

threading.Thread(target=worker, daemon=True).start()

# -------- ROUTES --------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/analyze", methods=["POST"])
def analyze():
    text = request.json.get("text","")

    if not text.startswith("http"):
        return {"error":"Sadece URL gir"}

    content = extract(text)
    r = risk(content)

    return {"risk":r,"label":"Şüpheli" if r>=50 else "Güvenli"}

@app.route("/api/all")
def all_data():
    return {"feed":feed,"stats":stats}

if __name__ == "__main__":
    app.run(debug=True)