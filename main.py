from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import time
import uvicorn

# 1. Initialize App
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"], 
 )

def init_db():
    conn = sqlite3.connect("jiahong.db")
    cursor = conn.cursor()
    # Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            phone TEXT PRIMARY KEY,
            username TEXT,
            password TEXT,
            referrer TEXT,
            balance REAL DEFAULT 0.0,
            commissions REAL DEFAULT 0.0
        )
    """)
    # Transactions Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            title TEXT,
            amount REAL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# 4. Data Models
class User(BaseModel):
    username: str
    phone: str
    password: str
    referrer: Optional[str] = None
    balance: float = 0.0
    commissions: float = 0.0

@app.post("/register")
async def register(user: User):
    conn = sqlite3.connect("jiahong.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, phone, password, referrer) VALUES (?, ?, ?, ?)",
                       (user.username, user.phone, user.password, user.referrer))
        conn.commit()
        return {"status": "success"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Phone already registered")
    finally:
        conn.close()

@app.post("/login")
async def login(phone: str, password: str):
    conn = sqlite3.connect("jiahong.db")
    conn.row_factory = sqlite3.Row # Allows accessing columns by name
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE phone = ? AND password = ?", (phone, password))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return dict(user)

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
    
@app.post("/process-commission")
async def process_commission(buyer_phone: str, amount: float):
    conn = sqlite3.connect("jiahong.db")
    cursor = conn.cursor()
    
    # 1. Find the referrer
    cursor.execute("SELECT referrer FROM users WHERE phone = ?", (buyer_phone,))
    res = cursor.fetchone()
    if res and res[0]:
        lvl1_phone = res[0]
        reward = amount * 0.10 # 10% Commission
        
        # 2. Update Referrer Balance
        cursor.execute("UPDATE users SET balance = balance + ?, commissions = commissions + ? WHERE phone = ?", 
                       (reward, reward, lvl1_phone))
        
        # 3. Log it
        cursor.execute("INSERT INTO transactions (phone, title, amount) VALUES (?, ?, ?)",
                       (lvl1_phone, f"Ref Commission from {buyer_phone}", reward))
        
    conn.commit()
    conn.close()
    return {"status": "commissions processed"}

# 6. Server Runner for Pydroid / Render
if __name__ == "__main__":
    # Note: Render provides a PORT environment variable, 
    # but 10000 is their default internal port.
    uvicorn.run(app, host="0.0.0.0", port=10000)