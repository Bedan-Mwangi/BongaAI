
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, JSON, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime, os, json, urllib.parse
from dotenv import load_dotenv
from typing import Optional, List, Dict

load_dotenv()
app = FastAPI(title="BongaAI Multi-Business Brain")

BOT_NAME = "BongaAI"
PROVIDER = os.getenv("LLM_PROVIDER", "groq")

Base = declarative_base()

class Business(Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True)  # e.g. gathiga-salon
    industry = Column(String)  # retail, salon, restaurant, clinic, hardware, etc
    phone = Column(String)  # business whatsapp number id
    description = Column(Text)
    config = Column(JSON, default={})  # full customizable brain
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    business_slug = Column(String, index=True)
    customer_phone = Column(String)
    customer_name = Column(String, default="")
    items = Column(Text)
    address = Column(Text)
    status = Column(String, default="new")  # new, confirmed, delivered
    total = Column(String, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

engine = create_engine("sqlite:///./bonga.db")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
sessions: Dict[str, dict] = {}  # phone+slug -> state

# --- DEFAULT BUSINESS TEMPLATES ---
TEMPLATES = {
    "retail": {
        "greeting": "Karibu! 🛒 I'm {bot_name} for {business_name}. I can help you browse products, place orders & track delivery.",
        "products": [{"name": "Example Product", "price": "500 KES"}],
        "services": [],
        "faq": "Hours: Mon-Sat 9am-6pm\nDelivery: 200 KES within Gathiga\nPayment: M-Pesa + COD",
        "tone": "Friendly Kenyan, use sheng sparingly, helpful",
        "collect_address": True,
        "collect_datetime": False
    },
    "salon": {
        "greeting": "Poa! 💇‍♀️ Karibu to {business_name}. I'm {bot_name}, nataka kukusaidia kubook appointment?",
        "products": [],
        "services": [{"name": "Braiding", "price": "1500 KES", "duration": "2h"}, {"name": "Manicure", "price": "800 KES"}],
        "faq": "Hours: Tue-Sun 8am-7pm\nLocation: Gathiga\nDeposit: 200 via M-Pesa",
        "tone": "Warm, girly, uses sheng, emoji friendly",
        "collect_address": False,
        "collect_datetime": True
    },
    "restaurant": {
        "greeting": "Sasa! 🍗 Karibu to {business_name}. Niaje, unataka kuorder nini leo?",
        "products": [{"name": "Kuku Choma + Ugali", "price": "600 KES"}, {"name": "Pilau Kuku", "price": "450 KES"}],
        "services": [],
        "faq": "Open daily 10am-10pm\nDelivery 30-45min\nFree delivery over 1000 KES",
        "tone": "Super casual, foodie, sheng heavy, funny",
        "collect_address": True,
        "collect_datetime": False
    },
    "clinic": {
        "greeting": "Hello, welcome to {business_name} 🏥 I'm {bot_name}. How can I help you book an appointment?",
        "products": [],
        "services": [{"name": "Consultation", "price": "1000 KES"}],
        "faq": "Open Mon-Sat 8am-5pm\nEmergency: Call 071...\nNHIF accepted",
        "tone": "Professional, empathetic, clear",
        "collect_address": False,
        "collect_datetime": True
    }
}

def get_business(slug: str = None):
    db = Session()
    # If no slug, use env or first business or create default
    if not slug:
        slug = os.getenv("BUSINESS_SLUG", "default")
    biz = db.query(Business).filter(Business.slug == slug).first()
    if not biz:
        # Auto-create default business for backwards compat
        if slug == "default":
            biz = Business(
                name=os.getenv("BUSINESS_NAME", "BongaAI Demo Shop"),
                slug="default",
                industry="retail",
                description="Demo shop in Gathiga",
                config=TEMPLATES["retail"]
            )
            db.add(biz); db.commit(); db.refresh(biz)
        else:
            return None
    db.close()
    return biz

def ask_llm(msg: str, business: Business, history: List[dict] = None):
    cfg = business.config or {}
    industry = business.industry or "retail"
    template = TEMPLATES.get(industry, TEMPLATES["retail"])
    # Merge template defaults with business config
    merged = {**template, **cfg}
    
    system_prompt = f"""
You are {BOT_NAME}, AI assistant for {business.name}.
Business: {business.description}
Industry: {industry}
Tone: {merged.get('tone','Friendly Kenyan')}
FAQ: {merged.get('faq','')}
Products: {json.dumps(merged.get('products',[]))}
Services: {json.dumps(merged.get('services',[]))}

Rules:
- Respond in same language customer uses (English/Swahili/Sheng)
- Keep replies short (under 3 lines), WhatsApp friendly
- If customer wants to order/book, say INTENT: order or INTENT: appointment
- If just chatting/FAQ, INTENT: faq
- Return JSON: {{"intent":"order|appointment|faq", "reply":"your reply"}}
- Use business name: {business.name}
"""
    try:
        if PROVIDER == "groq" and os.getenv("GROQ_API_KEY"):
            from groq import Groq
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            messages = [{"role": "system", "content": system_prompt}]
            if history:
                messages.extend(history[-4:])
            messages.append({"role": "user", "content": msg})
            c = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                response_format={"type": "json_object"}
            )
            return json.loads(c.choices[0].message.content)
    except Exception as e:
        print(f"LLM error: {e}")
    
    # Fallback keyword logic
    m = msg.lower()
    if any(x in m for x in ["order","buy","nunua","kula","choma","nataka"]):
        return {"intent":"order","reply": f"Sawa! What would you like from {business.name}? 😊"}
    if any(x in m for x in ["book","appointment","cut","massage","clinic","reserve"]):
        return {"intent":"appointment","reply": f"Poa! Which service at {business.name} unataka kubook?"}
    return {"intent":"faq","reply": f"Hey! I'm {BOT_NAME} for {business.name} 🤖 I can take orders, book appointments, or answer questions. Unataka nini?"}

def handle_conversation(phone: str, text: str, business_slug: str):
    business = get_business(business_slug)
    if not business:
        return f"Business {business_slug} not found."
    
    key = f"{business_slug}:{phone}"
    state = sessions.get(key, {"step":"idle", "history":[]})
    
    # Continue multi-step flows
    if state["step"] == "await_items":
        state["data"]["items"] = text
        cfg = business.config or {}
        if cfg.get("collect_address", True):
            state["step"] = "await_address"
            sessions[key] = state
            return f"Nice: {text} 👌 Where should we deliver? Tuma location ama address."
        else:
            # No address needed (salon/clinic)
            state["step"] = "await_datetime"
            sessions[key] = state
            return "Sawa! When do you want it? e.g. Kesho 2pm"

    if state["step"] == "await_address":
        db = Session()
        o = Order(business_slug=business_slug, customer_phone=phone, items=state["data"]["items"], address=text)
        db.add(o); db.commit()
        sessions[key] = {"step":"idle", "history":[]}
        db.close()
        return f"✅ Asante! Order #{o.id} confirmed at {business.name}: {state['data']['items']} -> {text}. Tutakuletea!"

    if state["step"] == "await_service":
        state["data"]["service"] = text
        state["step"] = "await_datetime"
        sessions[key] = state
        return "Perfect! When? e.g. Tomorrow 2pm ama leo 4pm"

    if state["step"] == "await_datetime":
        db = Session()
        o = Order(business_slug=business_slug, customer_phone=phone, items=f"APPT: {state['data'].get('service', state['data'].get('items',''))} at {text}", address=text)
        db.add(o); db.commit()
        sessions[key] = {"step":"idle", "history":[]}
        db.close()
        return f"✅ Booked at {business.name}! {state['data'].get('service','')} on {text}. Ref #{o.id}. Tutaonana!"

    # New intent detection
    ai = ask_llm(text, business, state.get("history",[]))
    intent = ai.get("intent","faq")
    reply = ai.get("reply","")
    
    # Save history
    state["history"] = (state.get("history",[]) + [{"role":"user","content":text},{"role":"assistant","content":reply}])[-10:]
    
    if intent == "order":
        state["step"] = "await_items"
        state["data"] = {}
        sessions[key] = state
    elif intent == "appointment":
        state["step"] = "await_service"
        state["data"] = {}
        sessions[key] = state
        # If services known, list them
        services = (business.config or {}).get("services",[])
        if services:
            list_txt = "\n".join([f"- {s['name']} ({s['price']})" for s in services[:5]])
            reply += f"\n\nServices:\n{list_txt}"
    else:
        sessions[key] = state
    
    return reply

# --- API Models ---
class Incoming(BaseModel):
    phone: str
    message: str
    business_slug: Optional[str] = "default"

class BusinessCreate(BaseModel):
    name: str
    slug: str
    industry: str = "retail"
    description: str = ""
    config: Optional[Dict] = None

class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict] = None

# --- Routes ---
@app.post("/message")
@app.post("/message/{business_slug}")
def incoming(data: Incoming, business_slug: str = "default"):
    # business_slug from path overrides body
    slug = business_slug if business_slug != "default" or data.business_slug == "default" else data.business_slug
    if data.business_slug != "default":
        slug = data.business_slug
    # If path param provided explicitly, use it
    # FastAPI will inject path param if route matches
    return {"reply": handle_conversation(data.phone, data.message, slug)}

@app.get("/")
def home():
    db = Session()
    count = db.query(Business).count()
    db.close()
    return {"bot": BOT_NAME, "status": "online", "businesses": count, "docs": "/docs", "admin": "/admin"}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/qr")
def qr_page():
    from fastapi.responses import HTMLResponse
    import os
    qr_txt = ""
    for f in ["baileys_auth_v2/qr.txt", "baileys_auth/qr.txt", "qr.txt"]:
        if os.path.exists(f):
            try:
                with open(f) as fp:
                    qr_txt = fp.read().strip()
                if qr_txt:
                    break
            except:
                pass
    if not qr_txt:
        return HTMLResponse("<h2>Waiting for QR... Refresh in 3s</h2><script>setTimeout(()=>location.reload(),3000)</script>")
    encoded = urllib.parse.quote(qr_txt)
    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>BongaAI QR</title>
    <style>body{{font-family:sans-serif;text-align:center;padding:20px;background:#f0f2f5}} img{{border:20px solid white;box-shadow:0 4px 20px rgba(0,0,0,0.2);border-radius:12px}} h1{{color:#075E54}}</style>
    </head><body>
    <h1>BongaAI QR - Scan in WhatsApp</h1>
    <p>Linked Devices > Link a Device</p>
    <img src='https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={encoded}' />
    <p><small>QR expires 20s - refresh</small></p>
    <a href='/qr'>Refresh</a>
    <script>setTimeout(()=>location.reload(),20000)</script>
    </body></html>
    """
    return HTMLResponse(html)

# --- Business Admin APIs ---
@app.get("/businesses")
def list_businesses():
    db = Session()
    bizs = db.query(Business).all()
    db.close()
    return [{"id":b.id,"name":b.name,"slug":b.slug,"industry":b.industry,"description":b.description} for b in bizs]

@app.post("/businesses")
def create_business(data: BusinessCreate):
    db = Session()
    if db.query(Business).filter(Business.slug==data.slug).first():
        db.close()
        raise HTTPException(400, "Slug already exists")
    template = TEMPLATES.get(data.industry, TEMPLATES["retail"])
    cfg = data.config or template
    # merge with template defaults
    merged = {**template, **(data.config or {})}
    biz = Business(name=data.name, slug=data.slug, industry=data.industry, description=data.description, config=merged)
    db.add(biz); db.commit(); db.refresh(biz)
    db.close()
    return {"ok": True, "business": {"slug": biz.slug, "name": biz.name}}

@app.get("/businesses/{slug}")
def get_biz(slug: str):
    db = Session()
    biz = db.query(Business).filter(Business.slug==slug).first()
    if not biz:
        db.close()
        raise HTTPException(404, "Not found")
    result = {"id":biz.id,"name":biz.name,"slug":biz.slug,"industry":biz.industry,"description":biz.description,"config":biz.config}
    db.close()
    return result

@app.put("/businesses/{slug}")
def update_biz(slug: str, data: BusinessUpdate):
    db = Session()
    biz = db.query(Business).filter(Business.slug==slug).first()
    if not biz:
        db.close()
        raise HTTPException(404, "Not found")
    if data.name: biz.name = data.name
    if data.industry: biz.industry = data.industry
    if data.description: biz.description = data.description
    if data.config:
        # merge
        biz.config = {**(biz.config or {}), **data.config}
    db.commit()
    db.close()
    return {"ok": True}

@app.get("/businesses/{slug}/orders")
def list_orders(slug: str):
    db = Session()
    orders = db.query(Order).filter(Order.business_slug==slug).order_by(Order.id.desc()).limit(50).all()
    db.close()
    return [{"id":o.id,"phone":o.customer_phone,"items":o.items,"address":o.address,"status":o.status,"created_at":o.created_at} for o in orders]

@app.get("/admin", response_class=HTMLResponse)
def admin():
    db = Session()
    bizs = db.query(Business).all()
    html = """
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>BongaAI Admin</title>
    <style>body{font-family:sans-serif;padding:20px;max-width:900px;margin:auto} .card{border:1px solid #ddd;padding:15px;border-radius:10px;margin:10px 0} input,select,textarea{width:100%;padding:8px;margin:5px 0} button{background:#075E54;color:white;padding:10px;border:none;border-radius:6px;cursor:pointer}</style>
    </head><body>
    <h1>BongaAI - Multi-Business Admin</h1>
    <p><a href='/docs'>API Docs</a> | <a href='/qr'>QR Scan</a></p>
    <h2>Create New Business</h2>
    <div class=card>
    <input id=name placeholder="Business Name e.g. Gathiga Salon">
    <input id=slug placeholder="slug e.g. gathiga-salon (no spaces)">
    <select id=industry><option value=retail>Retail/Shop</option><option value=salon>Salon/Spa</option><option value=restaurant>Restaurant</option><option value=clinic>Clinic</option><option value=hardware>Hardware</option></select>
    <textarea id=desc placeholder="Description e.g. Best salon in Gathiga, braiding, manicure"></textarea>
    <button onclick="createBiz()">Create Business</button>
    </div>
    <h2>Existing Businesses</h2>
    <div id=list>
    """
    for b in bizs:
        html += f"<div class=card><b>{b.name}</b> ({b.industry}) - <code>{b.slug}</code><br>{b.description}<br><a href='/businesses/{b.slug}/orders' target=_blank>View Orders</a> | <a href='/admin/edit?slug={b.slug}'>Edit Config</a></div>"
    html += """
    </div>
    <script>
    async function createBiz(){
      const body={name:document.getElementById('name').value, slug:document.getElementById('slug').value, industry:document.getElementById('industry').value, description:document.getElementById('desc').value}
      if(!body.name||!body.slug) return alert('Name and slug required');
      const res=await fetch('/businesses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const data=await res.json();
      if(res.ok){ alert('Created!'); location.reload(); } else alert(JSON.stringify(data));
    }
    </script>
    </body></html>
    """
    db.close()
    return HTMLResponse(html)
