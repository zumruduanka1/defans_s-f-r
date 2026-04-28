from flask import Flask, request, jsonify
import requests, os, smtplib, threading, time, re, html
from email.mime.text import MIMEText

app = Flask(__name__)

HF_API_KEY = os.getenv("HF_API_KEY")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_TO = os.getenv("EMAIL_TO")

history, feed, alerts = [], [], []

# ---------------- TEXT ----------------
def extract_text(url):
    try:
        r = requests.get(url, timeout=6, headers={"User-Agent":"Mozilla/5.0"})
        txt = re.sub("<[^<]+?>"," ",r.text)
        txt = html.unescape(txt)
        return " ".join(txt.split())[:2000]
    except:
        return ""

# ---------------- IMAGE ANALYSIS ----------------
def analyze_image(url):
    try:
        r = requests.post(
            "https://api-inference.huggingface.co/models/google/vit-base-patch16-224",
            headers={"Authorization": f"Bearer {HF_API_KEY}"},
            json={"inputs": url},
            timeout=8
        )
        return 30  # görselde düşük güven
    except:
        return 0

# ---------------- AI ----------------
def ai_score(text):
    try:
        r = requests.post(
            "https://api-inference.huggingface.co/models/facebook/bart-large-mnli",
            headers={"Authorization": f"Bearer {HF_API_KEY}"},
            json={
                "inputs": text,
                "parameters":{"candidate_labels":["yalan","doğru"]}
            },
            timeout=8
        )
        d = r.json()
        if isinstance(d,list):
            return int(d[0]["scores"][0]*100)
    except:
        return None

# ---------------- RISK ----------------
def risk_score(text):
    t = text.lower()
    score = 10

    for k in ["şok","gizli","ifşa","komplo","iddia","son dakika"]:
        if k in t:
            score += 15

    ai = ai_score(text)
    if ai:
        score = int(score*0.3 + ai*0.7)

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

# ---------------- RSS ----------------
def fetch_news():
    urls = [
        "https://news.google.com/rss?hl=tr&gl=TR&ceid=TR:tr",
        "https://www.trthaber.com/rss/manset.rss"
    ]

    data = []

    for u in urls:
        try:
            r = requests.get(u, timeout=5)
            items = re.findall(r"<item>(.*?)</item>", r.text, re.S)

            for i in items[:10]:
                title = re.search(r"<title>(.*?)</title>", i)
                link = re.search(r"<link>(.*?)</link>", i)

                if title:
                    data.append({
                        "text": html.unescape(title.group(1)),
                        "url": link.group(1) if link else None
                    })
        except:
            pass

    return data

# ---------------- FALLBACK SOCIAL ----------------
def fake_social_stream():
    return [
        {"text":"Şok iddia gündemde!", "url":None},
        {"text":"Bu haber gerçek mi tartışılıyor", "url":None},
        {"text":"Sosyal medyada yayılan iddia", "url":None}
    ]

# ---------------- SCAN ----------------
def scan():
    global feed, alerts

    items = fetch_news()

    if not items:
        items = fake_social_stream()

    new_feed, new_alerts = [], []

    for item in items:
        text = item["text"]

        if item["url"]:
            content = extract_text(item["url"])
            if len(content) > 100:
                text = content

        r = risk_score(text)

        obj = {"text": item["text"][:100], "risk": r}
        new_feed.append(obj)

        if r >= 50:
            new_alerts.append(obj)
            send_email(text, r)

    feed = new_feed[:20]
    alerts = new_alerts[:10]

def worker():
    while True:
        scan()
        time.sleep(40)

scan()
threading.Thread(target=worker, daemon=True).start()

# ---------------- API ----------------
@app.route("/api/analyze", methods=["POST"])
def analyze():
    text = request.json.get("text")

    if text.startswith("http"):
        if any(x in text for x in [".jpg",".png",".jpeg"]):
            r = analyze_image(text)
        else:
            text = extract_text(text)
            r = risk_score(text)
    else:
        r = risk_score(text)

    label = "Şüpheli" if r>=50 else "Güvenli"

    history.insert(0, {"text": text[:80], "risk": r})

    if r>=50:
        send_email(text, r)

    return {"risk":r,"label":label}

@app.route("/api/all")
def all_data():
    return {"feed":feed,"alerts":alerts,"history":history}

# ---------------- UI ----------------
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
    font-family:Arial;
    background:#020617;
    color:white;
}
.container {
    max-width:1100px;
    margin:auto;
    padding:40px;
}
h1 {
    text-align:center;
    font-size:40px;
}
.grid {
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:20px;
    margin-top:30px;
}
.card {
    background:#0f172a;
    padding:20px;
    border-radius:12px;
}
textarea {
    width:100%;
    height:120px;
    background:#020617;
    color:white;
    border:none;
    border-radius:10px;
    padding:10px;
}
button {
    width:100%;
    padding:12px;
    margin-top:10px;
    background:#6366f1;
    border:none;
    border-radius:10px;
    color:white;
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

<div class="container">

<h1>Dezenformasyona Karşı Yapay Zeka Kalkanı</h1>

<div class="grid">

<div class="card">
<textarea id="text" placeholder="URL gir..."></textarea>
<button onclick="analyze()">Analiz Et</button>
<h3 id="res"></h3>
</div>

<div class="card">
<h3>Sonuçlar</h3>
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

 let h=""

 d.history.forEach(x=>{
  let cls=x.risk>=50?"risk":"safe"
  h+=`<div class="item ${cls}">${x.text} (%${x.risk})</div>`
 })

 document.getElementById("history").innerHTML=h
}

setInterval(load,4000)
load()

</script>

</body>
</html>
"""