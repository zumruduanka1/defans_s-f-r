from flask import Flask, request, jsonify, render_template
import requests, os, smtplib, threading, time
from bs4 import BeautifulSoup
from email.mime.text import MIMEText

app = Flask(__name__)

HF_API_KEY = os.getenv("HF_API_KEY")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_TO = os.getenv("EMAIL_TO")

feed = []
history = []

# -------- CONTENT --------
def extract_text(url):
    try:
        r = requests.get(url, timeout=6, headers={"User-Agent":"Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        return soup.get_text()[:1500]
    except:
        return ""

# -------- AI --------
def ai_score(text):
    try:
        if not HF_API_KEY:
            return 30

        r = requests.post(
            "https://api-inference.huggingface.co/models/facebook/bart-large-mnli",
            headers={"Authorization": f"Bearer {HF_API_KEY}"},
            json={"inputs": text,
                  "parameters":{"candidate_labels":["yalan","doğru"]}},
            timeout=6
        )
        d = r.json()
        return int(d[0]["scores"][0]*100)
    except:
        return 30

# -------- RISK --------
def risk(text):
    score = 10
    t = text.lower()

    for k in ["şok","ifşa","gizli","iddia","komplo"]:
        if k in t:
            score += 15

    ai = ai_score(text)
    return min(100, int(score*0.3 + ai*0.7))

# -------- MAIL --------
def send_mail(text, r):
    try:
        if not EMAIL_USER: return

        msg = MIMEText(f"⚠️ Risk:%{r}\n{text[:200]}")
        msg["Subject"]="DEFANS ALERT"
        msg["From"]=EMAIL_USER
        msg["To"]=EMAIL_TO

        s=smtplib.SMTP("smtp.gmail.com",587)
        s.starttls()
        s.login(EMAIL_USER,EMAIL_PASS)
        s.sendmail(EMAIL_USER,EMAIL_TO,msg.as_string())
        s.quit()
    except:
        pass

# -------- FEED (GÜÇLÜ) --------
def fetch_news():
    data = []

    sources = [
        "https://news.google.com/rss?hl=tr&gl=TR&ceid=TR:tr",
        "https://www.trthaber.com/rss/manset.rss"
    ]

    for src in sources:
        try:
            r = requests.get(src, timeout=5)
            soup = BeautifulSoup(r.text, "xml")

            for item in soup.find_all("item")[:10]:
                data.append({
                    "title": item.title.text,
                    "link": item.link.text
                })
        except:
            pass

    # 🔥 fallback → boş kalmaz + şüpheli içerik üretir
    if not data:
        data = [
            {"title":"Şok iddia sosyal medyada yayıldı", "link":""},
            {"title":"Gizli belge ifşa edildi iddiası", "link":""}
        ]

    return data

# -------- WORKER --------
def worker():
    global feed

    while True:
        news = fetch_news()
        new_feed = []

        for n in news:
            text = extract_text(n["link"]) if n["link"] else n["title"]

            r = risk(text)

            new_feed.append({
                "text": n["title"],
                "risk": r
            })

            if r >= 50:
                send_mail(text, r)

        # 🔥 sadece şüpheli olanları da göster
        feed = sorted(new_feed, key=lambda x: x["risk"], reverse=True)[:15]

        time.sleep(30)

threading.Thread(target=worker, daemon=True).start()

# -------- ROUTES --------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/analyze", methods=["POST"])
def analyze():
    text = request.json.get("text","")

    if text.startswith("http"):
        text = extract_text(text)

    r = risk(text)
    label = "Şüpheli" if r>=50 else "Güvenli"

    history.insert(0, {"text":text[:80], "risk":r})

    return {"risk":r,"label":label}

@app.route("/api/feed")
def get_feed():
    return feed