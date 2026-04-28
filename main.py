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
        if not HF_API_KEY:
            return None

        r = requests.post(
            "https://api-inference.huggingface.co/models/facebook/bart-large-mnli",
            headers={"Authorization": f"Bearer {HF_API_KEY}"},
            json={
                "inputs": text,
                "parameters":{
                    "candidate_labels":["yalan haber","doğru haber"]
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
        if not EMAIL_USER:
            print("EMAIL USER YOK")
            return

        msg = MIMEText(f"⚠️ Riskli içerik:\n\n{text}\n\nRisk:%{risk}")
        msg["Subject"] = "DEFANS UYARI"
        msg["From"] = EMAIL_USER
        msg["To"] = EMAIL_TO

        s = smtplib.SMTP("smtp.gmail.com",587)
        s.starttls()
        s.login(EMAIL_USER, EMAIL_PASS)
        s.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
        s.quit()

        print("MAIL GÖNDERİLDİ")

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
    try:
        r = requests.get("https://news.google.com/rss?hl=tr&gl=TR&ceid=TR:tr")
        items = r.text.split("<title>")[2:8]

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
    return """
<!DOCTYPE html>
<html>
<head>
<title>DEFANS</title>
<style>
body{background:#020617;color:white;font-family:Arial;margin:0}
.container{max-width:1200px;margin:auto;padding:40px}
h1{text-align:center;font-size:48px}

.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.card{background:#0f172a;padding:20px;border-radius:15px}

textarea{width:100%;padding:10px;background:#020617;color:white;border:none;border-radius:10px}
button{width:100%;padding:12px;background:#6366f1;border:none;border-radius:10px;color:white;margin-top:10px}

.item{padding:10px;border-bottom:1px solid #1e293b}
.risk{color:#ef4444}
.safe{color:#10b981}
.alert{color:#f97316}
</style>
</head>
<body>

<div class="container">
<h1>DEFANS</h1>

<div class="grid">
<div class="card">
<textarea id="text" placeholder="Metin veya link gir..."></textarea>
<button onclick="analyze()">Analiz Et</button>
<h2 id="res"></h2>
</div>

<div class="card">
<h3>⚠️ Riskli İçerikler</h3>
<div id="alerts"></div>
</div>
</div>

<div class="grid" style="margin-top:20px">
<div class="card">
<h3>Akış</h3>
<div id="feed"></div>
</div>

<div class="card">
<h3>Geçmiş</h3>
<div id="history"></div>
</div>
</div>

</div>

<script>
async function analyze(){
 let t=document.getElementById("text").value

 let r=await fetch("/api/analyze",{
  method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({text:t})
 })

 let d=await r.json()
 document.getElementById("res").innerText="Risk:%"+d.risk+" "+d.label
 load()
}

async function load(){
 let r=await fetch("/api/all")
 let d=await r.json()

 let f="",h="",a=""

 d.feed.forEach(x=>{
  let cls=x.risk>=50?"risk":"safe"
  f+=`<div class="item ${cls}">${x.text} (%${x.risk})</div>`
 })

 d.history.forEach(x=>{
  let cls=x.risk>=50?"risk":"safe"
  h+=`<div class="item ${cls}">${x.text} (%${x.risk})</div>`
 })

 d.alerts.forEach(x=>{
  a+=`<div class="item alert">${x.text} (%${x.risk})</div>`
 })

 document.getElementById("feed").innerHTML=f
 document.getElementById("history").innerHTML=h
 document.getElementById("alerts").innerHTML=a
}

setInterval(load,5000)
load()
</script>

</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)