from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import time

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows your UI to connect
    allow_methods=["*"],
    allow_headers=["*"],
)
# Simple In-Memory DB (Replace with SQLAlchemy/PostgreSQL for production)
db = {
    "users": {},
    "transactions": []
}

class User(BaseModel):
    username: str
    phone: str
    password: str
    referrer: Optional[str] = None
    balance: float = 0.0
    commissions: float = 0.0

@app.post("/register")
async def register(user: User):
    if user.phone in db["users"]:
        raise HTTPException(status_code=400, detail="Phone already registered")
    db["users"][user.phone] = user.dict()
    return {"status": "success"}

@app.post("/login")
async def login(phone: str, password: str):
    user = db["users"].get(phone)
    if not user or user["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

@app.post("/transaction")
async def create_transaction(phone: str, title: str, amount: float):
    if phone not in db["users"]:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update Balance
    db["users"][phone]["balance"] += amount
    
    # Log Transaction
    tx = {"phone": phone, "title": title, "amount": amount, "date": time.strftime("%Y-%m-%d")}
    db["transactions"].append(tx)
    return tx

@app.get("/team/{phone}")
async def get_team(phone: str):
    all_users = db["users"].values()
    l1 = [u for u in all_users if u["referrer"] == phone]
    l1_phones = [u["phone"] for u in l1]
    l2 = [u for u in all_users if u["referrer"] in l1_phones]
    return {"l1": len(l1), "l2": len(l2)}
    

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)