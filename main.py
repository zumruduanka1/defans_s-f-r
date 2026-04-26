from flask import Flask, request, jsonify, render_template_string
import requests, os, smtplib, threading, time
from email.mime.text import MIMEText
import feedparser

app = Flask(__name__)

# ENV
TW = os.getenv("TWITTER_BEARER")
HF_API_KEY = os.getenv("HF_API_KEY")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_TO = os.getenv("EMAIL_TO")

feed, alerts, history = [], [], []

# ---------------- MAIL ----------------
def send_mail(text, risk):
    try:
        if not EMAIL_USER: return
        msg = MIMEText(f"{text[:400]}\n\nRisk:%{risk}")
        msg["Subject"] = "DEFANS ALERT"

        s = smtplib.SMTP("smtp.gmail.com",587)
        s.starttls()
        s.login(EMAIL_USER, EMAIL_PASS)
        s.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
        s.quit()
    except:
        pass

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
                "parameters": {
                    "candidate_labels": ["dezenformasyon","güvenilir haber"]
                }
            },
            timeout=5
        )

        d = r.json()
        if isinstance(d, list):
            return int(d[0]["scores"][0] * 100)
    except:
        return None

# ---------------- SCORE ----------------
def score(text):
    t = text.lower()
    base = 20

    if any(x in t for x in ["şok","ifşa","gizli","yalan","komplo"]):
        base += 30
    if "iddia" in t:
        base += 20

    ai = ai_score(text)

    if ai:
        return min(100, int((base + ai) / 2))
    return min(100, base)

# ---------------- SOURCES ----------------
def get_sources():
    sources = []

    try:
        g = feedparser.parse("https://news.google.com/rss?hl=tr&gl=TR&ceid=TR:tr")
        for e in g.entries[:5]:
            sources.append(e.title)
    except:
        pass

    try:
        t = feedparser.parse("https://www.trthaber.com/rss/son-dakika.rss")
        for e in t.entries[:5]:
            sources.append(e.title)
    except:
        pass

    try:
        a = feedparser.parse("https://www.aa.com.tr/tr/rss/default?cat=guncel")
        for e in a.entries[:5]:
            sources.append(e.title)
    except:
        pass

    if TW:
        try:
            r = requests.get(
                "https://api.twitter.com/2/tweets/search/recent?query=haber lang:tr -is:retweet&max_results=5",
                headers={"Authorization": f"Bearer {TW}"}
            )
            data = r.json().get("data", [])
            for x in data:
                sources.append(x["text"])
        except:
            pass

    if not sources:
        sources = [
            "Sosyal medyada yayılan şok iddia",
            "Yanlış bilgi hızla yayılıyor",
            "Gündemde tartışma yaratan açıklama"
        ]

    return sources

# ---------------- WORKER ----------------
def worker():
    global feed, alerts
    while True:
        data = get_sources()
        f=[]; a=[]

        for t in data:
            r = score(t)
            f.append({"text":t,"risk":r})

            if r >= 40:
                a.append({"text":t,"risk":r})
                send_mail(t,r)

        feed = f
        alerts = a
        time.sleep(20)

threading.Thread(target=worker, daemon=True).start()

# ---------------- ANALYZE ----------------
@app.route("/api/analyze", methods=["POST"])
def analyze():
    url = request.json.get("text")

    if not url.startswith("http"):
        return {"error":"Sadece link gir"}

    try:
        text = requests.get(url, timeout=5).text[:1000]
    except:
        return {"error":"İçerik alınamadı"}

    r = score(text)

    history.insert(0, {"text":url,"risk":r})
    send_mail(text,r)

    return {"risk":r}

@app.route("/api/data")
def data():
    return {"feed":feed,"alerts":alerts,"history":history[:5]}

# ---------------- UI ----------------
@app.route("/")
def home():
    return render_template_string("""<!DOCTYPE html>
<html>
<head>
<title>DEFANS</title>
<style>
body{background:#020617;color:white;font-family:Arial;}
.container{max-width:1200px;margin:auto;padding:40px;}
h1{text-align:center;font-size:52px;font-weight:bold;background:linear-gradient(90deg,#60a5fa,#a78bfa);-webkit-background-clip:text;color:transparent;}
.subtitle{text-align:center;color:#94a3b8;margin-bottom:30px;}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;margin-bottom:20px;}
.stat{background:#0f172a;padding:20px;border-radius:15px;text-align:center;}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;}
.card{background:#0f172a;padding:20px;border-radius:15px;}
input{width:100%;padding:12px;border-radius:10px;background:#020617;color:white;border:1px solid #1e293b;}
button{width:100%;padding:14px;border:none;border-radius:12px;background:linear-gradient(90deg,#6366f1,#a855f7);color:white;margin-top:10px;}
.item{padding:10px;border-bottom:1px solid #1e293b;}
.bad{color:#f59e0b}
</style>
</head>
<body>
<div class="container">
<h1>DEFANS</h1>
<p class="subtitle">Sosyal Medya Dezenformasyon Analiz Sistemi</p>

<div class="stats">
 <div class="stat"><h2 id="total">0</h2><p>Toplam İçerik</p></div>
 <div class="stat"><h2 id="risk">0</h2><p>Riskli</p></div>
 <div class="stat"><h2 id="rate">0%</h2><p>Ortalama Risk</p></div>
</div>

<div class="grid">

<div class="card">
<h3>Yeni Analiz</h3>
<input id="url" placeholder="Haber / Tweet linki">
<button onclick="analyze()">Analiz Başlat</button>
<h2 id="result"></h2>
</div>

<div class="card">
<h3>⚠️ Riskli İçerikler</h3>
<div id="alerts"></div>
</div>

<div class="card">
<h3>📡 Sosyal Medya Akışı</h3>
<div id="feed"></div>
</div>

<div class="card">
<h3>📊 Son Analizler</h3>
<div id="history"></div>
</div>

</div>
</div>

<script>
async function analyze(){
 let url=document.getElementById("url").value
 let r=await fetch("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:url})})
 let d=await r.json()
 document.getElementById("result").innerText = d.risk ? "%"+d.risk : d.error
 load()
}

async function load(){
 let r=await fetch("/api/data")
 let d=await r.json()

 let f="",a="",h=""
 let total=0,risk=0,sum=0

 d.feed.forEach(x=>{f+=`<div class="item">${x.text} (%${x.risk})</div>`; total++; sum+=x.risk})
 d.alerts.forEach(x=>{a+=`<div class="item bad">${x.text} (%${x.risk})</div>`; risk++})
 d.history.forEach(x=>{h+=`<div class="item">${x.text} (%${x.risk})</div>`})

 document.getElementById("feed").innerHTML=f
 document.getElementById("alerts").innerHTML=a
 document.getElementById("history").innerHTML=h

 document.getElementById("total").innerText=total
 document.getElementById("risk").innerText=risk
 document.getElementById("rate").innerText = total ? Math.round(sum/total)+"%" : "0%"
}

setInterval(load,4000)
load()
</script>
</body>
</html>""")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)