from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime, os, json
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(title="BongaAI Brain")

BOT_NAME = "BongaAI"
PROVIDER = os.getenv("LLM_PROVIDER", "groq")

Base = declarative_base()
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    phone = Column(String)
    items = Column(String)
    address = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

engine = create_engine("sqlite:///./bonga.db")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
sessions = {}

FAQ = "Hours Mon-Sat 9-6, Location Gathiga, Delivery 200 KES, M-Pesa + COD"

def ask_llm(msg: str):
    try:
        if PROVIDER == "groq" and os.getenv("GROQ_API_KEY"):
            from groq import Groq
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            c = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": f"You are {BOT_NAME}, Bot Assistant: BongaAI. Kenyan assistant. FAQ: {FAQ}. Return JSON with intent and reply."},
                    {"role": "user", "content": msg}
                ],
                response_format={"type": "json_object"}
            )
            return json.loads(c.choices[0].message.content)
    except Exception as e:
        print(f"LLM error: {e}")
    # fallback
    m = msg.lower()
    if any(x in m for x in ["order","buy","nunua"]):
        return {"intent":"order","reply":"Sawa! What would you like to order?"}
    if any(x in m for x in ["book","appointment"]):
        return {"intent":"appointment","reply":"Poa! Which service to book?"}
    return {"intent":"faq","reply":"Hey! I'm BongaAI 🤖 I can answer questions, take orders, or book appointments. What do you need?"}

def handle_conversation(phone, text):
    state = sessions.get(phone, {"step":"idle"})
    if state["step"] == "await_items":
        state["data"] = {"items": text}
        state["step"] = "await_address"
        sessions[phone] = state
        return f"Got it: {text}. Where should we deliver?"
    if state["step"] == "await_address":
        db = Session()
        o = Order(phone=phone, items=state["data"]["items"], address=text)
        db.add(o); db.commit()
        sessions[phone] = {"step":"idle"}
        return f"✅ Asante! Order #{o.id} confirmed: {state['data']['items']} -> {text}"
    if state["step"] == "await_service":
        state["data"] = {"service": text}
        state["step"] = "await_datetime"
        sessions[phone] = state
        return "When? e.g. Tomorrow 2pm"
    if state["step"] == "await_datetime":
        db = Session()
        o = Order(phone=phone, items=f"APPT: {state['data']['service']} at {text}", address=text)
        db.add(o); db.commit()
        sessions[phone] = {"step":"idle"}
        return f"✅ Booked {state['data']['service']} on {text}. Ref #{o.id}"

    ai = ask_llm(text)
    intent = ai.get("intent","faq")
    reply = ai.get("reply","")
    if intent == "order":
        sessions[phone] = {"step":"await_items"}
    elif intent == "appointment":
        sessions[phone] = {"step":"await_service"}
    return reply

class Incoming(BaseModel):
    phone: str
    message: str

@app.post("/message")
def incoming(data: Incoming):
    return {"reply": handle_conversation(data.phone, data.message)}

@app.get("/")
def home():
    return {"bot": BOT_NAME, "status": "online", "docs": "/docs"}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/qr")
def qr_page():
    from fastapi.responses import HTMLResponse
    import os, glob
    qr_txt = ""
    for f in ["baileys_auth_v2/qr.txt", "baileys_auth/qr.txt", "qr.txt"]:
        if os.path.exists(f):
            try:
                with open(f) as fp:
                    qr_txt = fp.read().strip()
                break
            except: pass
    if not qr_txt:
        return HTMLResponse("<h2>Waiting for QR... Refresh in 5s</h2><script>setTimeout(()=>location.reload(),3000)</script>")
    # Use qrserver API to render scannable image
    import urllib.parse
    encoded = urllib.parse.quote(qr_txt)
    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'>
    <style>body{{font-family:sans-serif;text-align:center;padding:20px}} img{{border:20px solid white;box-shadow:0 4px 20px rgba(0,0,0,0.2)}} </style>
    </head><body>
    <h1>BongaAI QR - Scan in WhatsApp</h1>
    <p>WhatsApp > Linked Devices > Link a Device</p>
    <img src='https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={encoded}' />
    <p><small>QR refreshes every 20s - if expired, refresh page</small></p>
    <p><a href='/qr'>Refresh QR</a></p>
    <script>setTimeout(()=>location.reload(),20000)</script>
    </body></html>
    """
    return HTMLResponse(html)

