from flask import Flask, request, jsonify
import requests, os, smtplib, threading, time, re, html
from email.mime.text import MIMEText

app = Flask(__name__)

HF_API_KEY = os.getenv("HF_API_KEY")
TWITTER_BEARER = os.getenv("TWITTER_BEARER")

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_TO = os.getenv("EMAIL_TO")

history, feed, alerts = [], [], []

# ---------------- TEXT CLEAN ----------------
def extract_text(url):
    try:
        r = requests.get(url, timeout=6, headers={"User-Agent":"Mozilla/5.0"})
        html_txt = r.text

        html_txt = re.sub(r"<script.*?>.*?</script>", "", html_txt, flags=re.S)
        html_txt = re.sub(r"<style.*?>.*?</style>", "", html_txt, flags=re.S)

        text = re.sub("<[^<]+?>", "", html_txt)
        text = html.unescape(text)
        text = " ".join(text.split())

        return text[:2000]
    except:
        return ""

# ---------------- AI ----------------
def ai_score(text):
    try:
        if not HF_API_KEY:
            return None

        r = requests.post(
            "https://api-inference.huggingface.co/models/facebook/bart-large-mnli",
            headers={"Authorization": f"Bearer {HF_API_KEY}"},
            json={
                "inputs": text,
                "parameters":{"candidate_labels":["yalan haber","doğru haber"]}
            },
            timeout=8
        )

        d = r.json()
        if isinstance(d, list):
            return int(d[0]["scores"][0] * 100)
    except:
        return None

# ---------------- RISK ----------------
def risk_score(text):
    t = text.lower()
    score = 0

    for k in ["şok","gizli","ifşa","komplo","bomba iddia","yasaklandı","son dakika","iddia"]:
        if k in t:
            score += 12

    if "!" in text:
        score += 5

    ai = ai_score(text)
    if ai:
        score = int(score * 0.3 + ai * 0.7)

    return min(100, max(5, score))

# ---------------- MAIL ----------------
def send_email(text, risk):
    try:
        if not EMAIL_USER:
            return

        msg = MIMEText(f"⚠️ Risk:%{risk}\n\n{text[:400]}")
        msg["Subject"] = "DEFANS ALERT"
        msg["From"] = EMAIL_USER
        msg["To"] = EMAIL_TO

        s = smtplib.SMTP("smtp.gmail.com",587)
        s.starttls()
        s.login(EMAIL_USER, EMAIL_PASS)
        s.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
        s.quit()
    except:
        pass

# ---------------- RSS PARSER ----------------
def parse_rss(url):
    data = []
    try:
        r = requests.get(url, timeout=6)
        items = re.findall(r"<item>(.*?)</item>", r.text, re.S)

        for item in items[:10]:
            title = re.search(r"<title>(.*?)</title>", item)
            link = re.search(r"<link>(.*?)</link>", item)

            if title:
                t = html.unescape(title.group(1))
                if link:
                    data.append({"text": t, "url": link.group(1)})
                else:
                    data.append({"text": t, "url": None})
    except:
        pass

    return data

# ---------------- NEWS SOURCES ----------------
def fetch_news():
    sources = [
        "https://news.google.com/rss?hl=tr&gl=TR&ceid=TR:tr",
        "https://www.trthaber.com/rss/manset.rss",
        "https://www.hurriyet.com.tr/rss/anasayfa",
    ]

    all_data = []
    for s in sources:
        all_data += parse_rss(s)

    return all_data

# ---------------- TWITTER ----------------
def fetch_twitter():
    data = []

    if not TWITTER_BEARER:
        return data

    queries = [
        "gündem lang:tr",
        "son dakika lang:tr",
        "iddia lang:tr"
    ]

    try:
        headers = {"Authorization": f"Bearer {TWITTER_BEARER}"}

        for q in queries:
            r = requests.get(
                "https://api.twitter.com/2/tweets/search/recent",
                headers=headers,
                params={"query": q, "max_results": 10}
            )

            tweets = r.json().get("data", [])

            for t in tweets:
                data.append({"text": t["text"], "url": None})

    except:
        pass

    return data

# ---------------- SCAN ----------------
def scan():
    global feed, alerts

    items = fetch_twitter() + fetch_news()

    if not items:
        items = [{"text": "Gündem veri akışı bekleniyor...", "url": None}]

    new_feed = []
    new_alerts = []

    for item in items:
        text = item["text"]

        if item["url"]:
            content = extract_text(item["url"])
            if len(content) > 100:
                text = content

        r = risk_score(text)

        obj = {"text": item["text"][:120], "risk": r}
        new_feed.append(obj)

        if r >= 50:
            new_alerts.append(obj)
            send_email(text, r)

    feed = new_feed[:20]
    alerts = new_alerts[:10]

def worker():
    while True:
        scan()
        time.sleep(45)

scan()
threading.Thread(target=worker, daemon=True).start()

# ---------------- API ----------------
@app.route("/api/analyze", methods=["POST"])
def analyze():
    text = request.json.get("text")

    if text.startswith("http"):
        text = extract_text(text)

    if len(text) < 20:
        return {"risk":0,"label":"Yetersiz veri"}

    r = risk_score(text)
    label = "Şüpheli" if r>=50 else "Güvenli"

    history.insert(0, {"text": text[:80], "risk": r})

    if r>=50:
        send_email(text, r)

    return {"risk":r, "label":label}

@app.route("/api/all")
def all_data():
    return {"feed":feed,"alerts":alerts,"history":history}

# ---------------- UI (DOKUNMADIM) ----------------
@app.route("/")
def home():
    return open("ui.html").read()