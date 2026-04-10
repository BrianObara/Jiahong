
# main.py
import os
import json
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import time

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple File-based persistence for Render (survives restarts)
DB_FILE = "db.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"users": {}, "transactions": []}

def save_db(db_data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(db_data, f, indent=2)
    except Exception as e:
        print(f"Error saving DB: {e}")

db = load_db()

# --- Models ---

class User(BaseModel):
    username: str
    phone: str
    password: str
    referrer: Optional[str] = None
    balance: float = 0.0
    commissions: float = 0.0

class TransactionCreate(BaseModel):
    phone: str
    title: str
    amount: float

# --- Endpoints ---

@app.post("/register")
async def register(user: User):
    if user.phone in db["users"]:
        raise HTTPException(status_code=400, detail="Phone already registered")
    
    # Handle Pydantic v1 vs v2 compatibility
    user_data = user.model_dump() if hasattr(user, 'model_dump') else user.dict()
    
    # Ensure fields exist
    if "balance" not in user_data["balance"] == 0.0:
        return
    if "commissions" not in user_data["commissions"] == 0.0:
        return
    
    db["users"][user.phone] = user_data
    save_db(db)
    return {"status": "success"}

@app.post("/login")
# Frontend sends query params: ?phone=...&password=...
async def login(phone: str = Query(...), password: str = Query(...)):
    user = db["users"].get(phone)
    if not user or user.get("password") != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

@app.post("/transaction")
# Frontend sends JSON Body: { phone, title, amount }
async def create_transaction(tx: TransactionCreate):
    if tx.phone not in db["users"]:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update Balance safely
    current_user = db["users"][tx.phone]
    current_user["balance"] += tx.amount
    
    # Initialize commissions if missing
    current_user["commissions"] = current_user.get("commissions", 0.0)
    
    # Log Transaction
    new_tx = {
        "phone": tx.phone,
        "title": tx.title,
        "amount": tx.amount,
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "completed"
    }
    db["transactions"].append(new_tx)
    save_db(db)
    
    return new_tx

@app.get("/team/{phone}")
async def get_team(phone: str):
    all_users = list(db["users"].values())
    
    # Level 1: Users who referred to 'phone'
    l1 = [u for u in all_users if u.get("referrer") == phone]
    l1_phones = [u["phone"] for u in l1]
    
    # Level 2: Users who referred to any L1 user
    l2 = [u for u in all_users if u.get("referrer") in l1_phones]
    
    return {"l1": len(l1), "l2": len(l2)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
