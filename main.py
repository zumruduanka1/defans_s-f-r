from flask import Flask, request, jsonify
import requests, os, smtplib, threading, time, re
from email.mime.text import MIMEText

app = Flask(__name__)

HF_API_KEY = os.getenv("HF_API_KEY")
TWITTER_BEARER = os.getenv("TWITTER_BEARER")

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_TO = os.getenv("EMAIL_TO")

history = []
feed = []
alerts = []

# ---------------- TEXT CLEAN ----------------
def clean_html(html):
    text = re.sub("<[^<]+?>", "", html)
    return text[:1000]

# ---------------- AI ----------------
def ai_score(text):
    try:
        r = requests.post(
            "https://api-inference.huggingface.co/models/facebook/bart-large-mnli",
            headers={"Authorization": f"Bearer {HF_API_KEY}"},
            json={
                "inputs": text,
                "parameters":{
                    "candidate_labels":[
                        "yalan haber",
                        "doğru haber"
                    ]
                }
            },
            timeout=6
        )

        d = r.json()

        if isinstance(d, list):
            return int(d[0]["scores"][0]*100)

    except:
        return None

# ---------------- RISK ----------------
def risk_score(text):
    base = 10
    t = text.lower()

    if any(x in t for x in ["şok","gizli","ifşa","komplo"]):
        base += 30

    if any(x in t for x in ["iddia","son dakika","şüpheli"]):
        base += 20

    ai = ai_score(text)

    if ai:
        return int((base*0.3)+(ai*0.7))

    return base

# ---------------- MAIL ----------------
def send_email(text, risk):
    try:
        msg = MIMEText(f"⚠️ Riskli içerik:\n\n{text}\n\nRisk:%{risk}")
        msg["Subject"] = "DEFANS UYARI"
        msg["From"] = EMAIL_USER
        msg["To"] = EMAIL_TO

        s = smtplib.SMTP("smtp.gmail.com",587)
        s.starttls()
        s.login(EMAIL_USER, EMAIL_PASS)
        s.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
        s.quit()
    except Exception as e:
        print("MAIL ERROR:", e)

# ---------------- URL ----------------
def extract_text(url):
    try:
        r = requests.get(url, timeout=5)
        return clean_html(r.text)
    except:
        return url

# ---------------- TWITTER ----------------
def fetch_twitter():
    data = []

    try:
        headers = {"Authorization": f"Bearer {TWITTER_BEARER}"}
        params = {"query": "gündem lang:tr", "max_results": 10}

        r = requests.get(
            "https://api.twitter.com/2/tweets/search/recent",
            headers=headers, params=params
        )

        tweets = r.json().get("data", [])

        for t in tweets:
            data.append(t["text"])
    except:
        pass

    return data

# ---------------- NEWS ----------------
def fetch_news():
    data = []
    urls = [
        "https://news.google.com/rss?hl=tr&gl=TR&ceid=TR:tr"
    ]

    for u in urls:
        try:
            r = requests.get(u)
            items = r.text.split("<title>")[2:6]
            for i in items:
                data.append(i.split("</title>")[0])
        except:
            pass

    return data

# ---------------- SCAN ----------------
def scan():
    global feed, alerts

    texts = fetch_twitter() + fetch_news()

    if not texts:
        texts = ["Şok iddia gündemde"]

    new_feed = []
    new_alerts = []

    for t in texts:
        r = risk_score(t)
        item = {"text": t, "risk": r}

        new_feed.append(item)

        if r >= 50:
            new_alerts.append(item)
            send_email(t, r)

    feed = new_feed
    alerts = new_alerts

def worker():
    while True:
        scan()
        time.sleep(60)

scan()
threading.Thread(target=worker, daemon=True).start()

# ---------------- API ----------------
@app.route("/api/analyze", methods=["POST"])
def analyze():
    text = request.json.get("text")

    if text.startswith("http"):
        text = extract_text(text)

    r = risk_score(text)
    label = "Şüpheli" if r >= 50 else "Güvenli"

    history.insert(0, {"text": text[:200], "risk": r})

    if r >= 50:
        send_email(text, r)

    return {"risk": r, "label": label}

@app.route("/api/all")
def all_data():
    return {"feed": feed, "alerts": alerts, "history": history}

# ---------------- UI ----------------
@app.route("/")
def home():
    return "<h1 style='color:white;background:black;text-align:center'>DEFANS AKTİF</h1>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)