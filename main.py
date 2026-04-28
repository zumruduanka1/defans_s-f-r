from flask import Flask, request, jsonify
import requests, os, smtplib, threading, time, re
from email.mime.text import MIMEText

app = Flask(__name__)

HF_API_KEY = os.getenv("HF_API_KEY")
TWITTER_BEARER = os.getenv("TWITTER_BEARER")

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_TO = os.getenv("EMAIL_TO")

history, feed, alerts = [], [], []

# -------- TEXT --------
def extract_text(url):
    try:
        r = requests.get(url, timeout=5)
        html = re.sub(r"<script.*?>.*?</script>", "", r.text, flags=re.S)
        html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.S)
        text = re.sub("<[^<]+?>", "", html)
        return " ".join(text.split())[:1200]
    except:
        return ""

# -------- AI --------
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
            }, timeout=6
        )
        d = r.json()
        if isinstance(d, list):
            return int(d[0]["scores"][0]*100)
    except:
        return None

# -------- RISK --------
def risk_score(text):
    t = text.lower()
    score = 0

    for k in ["şok","gizli","ifşa","komplo","bomba iddia","yasaklandı"]:
        if k in t:
            score += 15

    ai = ai_score(text)
    if ai:
        score = int(score*0.4 + ai*0.6)

    return min(100, max(5, score))

# -------- MAIL --------
def send_email(text, risk):
    try:
        if not EMAIL_USER:
            return
        msg = MIMEText(f"Risk:%{risk}\n\n{text[:500]}")
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

# -------- SOURCES --------
def fetch_news():
    data=[]
    try:
        r=requests.get("https://news.google.com/rss?hl=tr&gl=TR&ceid=TR:tr")
        items=r.text.split("<title>")[2:10]
        for i in items:
            data.append(i.split("</title>")[0])
    except: pass
    return data

def scan():
    global feed, alerts
    texts = fetch_news()

    new_feed, new_alerts = [], []

    for t in texts:
        r = risk_score(t)
        item = {"text": t, "risk": r}
        new_feed.append(item)

        if r >= 50:
            new_alerts.append(item)

    feed = new_feed[:10]
    alerts = new_alerts[:5]

def worker():
    while True:
        scan()
        time.sleep(60)

scan()
threading.Thread(target=worker, daemon=True).start()

# -------- API --------
@app.route("/api/analyze", methods=["POST"])
def analyze():
    text = request.json.get("text")

    if text.startswith("http"):
        text = extract_text(text)

    r = risk_score(text)
    label = "Şüpheli" if r>=50 else "Güvenli"

    history.insert(0, {"text": text[:80], "risk": r})

    if r>=50:
        send_email(text, r)

    return {"risk":r, "label":label}

@app.route("/api/all")
def all_data():
    return {"feed":feed,"alerts":alerts,"history":history}

# -------- UI --------
@app.route("/")
def home():
    return """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>DEFANS PRO</title>

<style>
body {
    margin:0;
    font-family:Inter, sans-serif;
    background:linear-gradient(180deg,#020617,#020617);
    color:white;
}

.topbar {
    display:flex;
    justify-content:space-between;
    padding:20px 40px;
}

.logo {
    font-weight:700;
}

.badge {
    background:#1e293b;
    padding:6px 12px;
    border-radius:20px;
    font-size:12px;
}

.hero {
    text-align:center;
    margin-top:40px;
}

.hero h1 {
    font-size:44px;
    font-weight:800;
}

.hero p {
    color:#9ca3af;
    max-width:600px;
    margin:auto;
}

.stats {
    display:flex;
    justify-content:center;
    gap:20px;
    margin-top:30px;
}

.stat {
    background:#0f172a;
    padding:20px;
    border-radius:12px;
    text-align:center;
    width:120px;
}

.main {
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:20px;
    max-width:1100px;
    margin:40px auto;
}

.card {
    background:#0f172a;
    padding:20px;
    border-radius:16px;
}

textarea {
    width:100%;
    height:120px;
    background:#020617;
    border:none;
    border-radius:10px;
    color:white;
    padding:10px;
}

button {
    width:100%;
    padding:12px;
    margin-top:10px;
    border:none;
    border-radius:10px;
    background:linear-gradient(90deg,#6366f1,#8b5cf6);
    color:white;
    font-weight:600;
}

.item {
    padding:10px;
    border-bottom:1px solid #1e293b;
}

.risk {color:#f59e0b;}
.safe {color:#10b981;}
</style>
</head>

<body>

<div class="topbar">
<div class="logo">🛡 DEFANS PRO</div>
<div class="badge">AI Powered</div>
</div>

<div class="hero">
<h1>Dezenformasyona Karşı Yapay Zeka Kalkanı</h1>
<p>Yalan haberleri, manipülasyonu ve dezenformasyonu anında tespit edin.</p>

<div class="stats">
<div class="stat"><div id="total">0</div>Toplam</div>
<div class="stat"><div id="bad">0</div>Riskli</div>
<div class="stat"><div id="good">0</div>Güvenli</div>
</div>
</div>

<div class="main">

<div class="card">
<h3>Yeni Analiz</h3>
<textarea id="text" placeholder="URL gir..."></textarea>
<button onclick="analyze()">Analiz Başlat</button>
<h3 id="res"></h3>
</div>

<div class="card">
<h3>Son Analizler</h3>
<div id="history"></div>
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

 let h=""
 let total=0, bad=0, good=0

 d.history.forEach(x=>{
  total++
  if(x.risk>=50) bad++; else good++

  let cls=x.risk>=50?"risk":"safe"
  h+=`<div class="item ${cls}">${x.text} (%${x.risk})</div>`
 })

 document.getElementById("history").innerHTML=h
 document.getElementById("total").innerText=total
 document.getElementById("bad").innerText=bad
 document.getElementById("good").innerText=good
}

setInterval(load,4000)
load()

</script>

</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)