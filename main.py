from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
import time
import uvicorn

# 1. Initialize App
app = FastAPI()

# 2. Correct Middleware Setup (Must be after app initialization)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Simple In-Memory Database
db = {
    "users": {},
    "transactions": []
}

# 4. Data Models
class User(BaseModel):
    username: str
    phone: str
    password: str
    referrer: Optional[str] = None
    balance: float = 0.0
    commissions: float = 0.0

# 5. Routes
@app.post("/register")
async def register(user: User):
    if user.phone in db["users"]:
        raise HTTPException(status_code=400, detail="Phone already registered")
    
    # Save user to memory
    db["users"][user.phone] = user.dict()
    return {"status": "success", "message": "Registered"}

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
    
    # Update Balance logic
    db["users"][phone]["balance"] += amount
    
    tx = {
        "phone": phone, 
        "title": title, 
        "amount": amount, 
        "date": time.strftime("%Y-%m-%d")
    }
    db["transactions"].append(tx)
    return tx

@app.get("/team/{phone}")
async def get_team(phone: str):
    all_users = db["users"].values()
    # Filter users who were referred by this phone number
    team = [u for u in all_users if u.get("referrer") == phone]
    return team

# 6. Server Runner for Pydroid / Render
if __name__ == "__main__":
    # Note: Render provides a PORT environment variable, 
    # but 10000 is their default internal port.
    uvicorn.run(app, host="0.0.0.0", port=10000)