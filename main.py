import sqlite3
import uvicorn
import asyncio
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta

# Investment Plans (Must match frontend IDs)
PLANS = {
    1: {'name': 'Alpha Starter', 'price': 100, 'roi': 5, 'duration': 7},
    2: {'name': 'Pro Yield', 'price': 500, 'roi': 8, 'duration': 14},
    3: {'name': 'Titan Fund', 'price': 2000, 'roi': 12, 'duration': 30}
}

RENDER_URL = "https://jiahong.onrender.com/health"

async def keep_alive():
    """Background task that pings the server every 10 minutes."""
    async with httpx.AsyncClient() as client:
        while True:
            try:
                response = await client.get(RENDER_URL)
                print(f"Self-ping successful: {response.status_code}")
            except Exception as e:
                print(f"Self-ping failed: {e}")
            
            # Wait for 10 minutes (600 seconds)
            await asyncio.sleep(600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs when the server starts
    asyncio.create_task(keep_alive())
    yield
    # This runs when the server shuts down

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Database Setup ---

def get_db():
    conn = sqlite3.connect("jiahong.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                phone TEXT PRIMARY KEY,
                username TEXT,
                password TEXT,
                referrer TEXT,
                balance REAL DEFAULT 0.0,
                commissions REAL DEFAULT 0.0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS investments (
                uid INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT,
                plan_id INTEGER,
                plan_name TEXT,
                price REAL,
                roi REAL,
                expiry TIMESTAMP,
                last_claimed_date TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT,
                title TEXT,
                amount REAL,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
init_db()

# --- Models ---

class UserReg(BaseModel):
    username: str
    phone: str
    password: str
    referrer: Optional[str] = None

class UserUpdate(BaseModel):
    phone: str
    username: Optional[str] = None
    balance: Optional[float] = None
    commissions: Optional[float] = None
    # Add other fields here if you want them updatable

# --- New Endpoints for auth object ---
@app.get("/my-investments")
async def get_my_investments(phone: str):
    """
    Retrieves all investment plans associated with a specific phone number.
    """
    with get_db() as conn:
        # We select everything from the investments table for this user
        # You can also add 'ORDER BY uid DESC' to show the newest ones first
        investments = conn.execute(
            "SELECT * FROM investments WHERE phone = ? ORDER BY uid DESC", 
            (phone,)
        ).fetchall()
        
        # Convert the sqlite3.Row objects into a list of dictionaries for JSON response
        return [dict(inv) for inv in investments]

@app.get("/users")
async def get_all_users():
    """Returns a list of all registered users."""
    with get_db() as conn:
        users = conn.execute("SELECT * FROM users").fetchall()
        return [dict(u) for u in users]

@app.put("/users/update")
async def update_user(user_data: UserUpdate):
    """Updates a user's profile and returns the updated user object."""
    with get_db() as conn:
        # Check if user exists first
        existing = conn.execute("SELECT * FROM users WHERE phone = ?", (user_data.phone,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Build dynamic update query based on provided fields
        update_fields = []
        params = []
        
        for field, value in user_data.dict(exclude_unset=True).items():
            if field != "phone": # Don't update the primary key
                update_fields.append(f"{field} = ?")
                params.append(value)
        
        if not update_fields:
            return dict(existing)

        params.append(user_data.phone)
        query = f"UPDATE users SET {', '.join(update_fields)} WHERE phone = ?"
        
        conn.execute(query, tuple(params))
        conn.commit()
        
        # Fetch the updated version to return to the frontend
        updated = conn.execute("SELECT * FROM users WHERE phone = ?", (user_data.phone,)).fetchone()
        return dict(updated)

# --- Existing Endpoints ---

@app.post("/register")
async def register(user: UserReg):
    with get_db() as conn:
        try:
            conn.execute("INSERT INTO users (username, phone, password, referrer) VALUES (?, ?, ?, ?)",
                         (user.username, user.phone, user.password, user.referrer))
            conn.commit()
            return {"status": "success"}
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Phone already registered")

@app.post("/login")
async def login(phone: str, password: str):
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE phone = ? AND password = ?", (phone, password)).fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return dict(user)

@app.post("/transaction")
async def create_transaction(phone: str, title: str, amount: float):
    with get_db() as conn:
        user_check = conn.execute("SELECT phone FROM users WHERE phone = ?", (phone,)).fetchone()
        if not user_check:
            raise HTTPException(status_code=404, detail="User not found")
            
        conn.execute("UPDATE users SET balance = balance + ? WHERE phone = ?", (amount, phone))
        conn.execute("INSERT INTO transactions (phone, title, amount) VALUES (?, ?, ?)", (phone, title, amount))
        conn.commit()
        
        user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        return dict(user)

@app.get("/team/{phone}")
async def get_team(phone: str):
    with get_db() as conn:
        team = conn.execute("SELECT * FROM users WHERE referrer = ?", (phone,)).fetchall()
        return [dict(u) for u in team]
        

@app.post("/invest/purchase")
async def purchase_plan(phone: str, plan_id: int):
    plan = PLANS.get(plan_id)
    if not plan: raise HTTPException(status_code=400, detail="Invalid Plan")

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        if user['balance'] < plan['price']:
            raise HTTPException(status_code=400, detail="Insufficient Balance")

        # 1. Deduct Balance
        conn.execute("UPDATE users SET balance = balance - ? WHERE phone = ?", (plan['price'], phone))
        
        # 2. Add Investment
        expiry = datetime.now() + timedelta(days=plan['duration'])
        conn.execute("""INSERT INTO investments (phone, plan_id, plan_name, price, roi, expiry) 
                     VALUES (?, ?, ?, ?, ?, ?)""", 
                     (phone, plan_id, plan['name'], plan['price'], plan['roi'], expiry))
        
        # 3. Log Transaction
        conn.execute("INSERT INTO transactions (phone, title, amount) VALUES (?, ?, ?)", 
                     (phone, f"Invest: {plan['name']}", -plan['price']))
        
        # 4. Commission Logic (L1 and L2)
        if user['referrer']:
            # L1
            l1_bonus = plan['price'] * 0.10
            conn.execute("UPDATE users SET balance = balance + ?, commissions = commissions + ? WHERE phone = ?", 
                         (l1_bonus, l1_bonus, user['referrer']))
            
            # L2
            l1_user = conn.execute("SELECT referrer FROM users WHERE phone = ?", (user['referrer'],)).fetchone()
            if l1_user and l1_user['referrer']:
                l2_bonus = plan['price'] * 0.05
                conn.execute("UPDATE users SET balance = balance + ?, commissions = commissions + ? WHERE phone = ?", 
                             (l2_bonus, l2_bonus, l1_user['referrer']))
        
        conn.commit()
        return {"status": "success"}

@app.post("/invest/claim")
async def claim_task(phone: str, investment_uid: int):
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        inv = conn.execute("SELECT * FROM investments WHERE uid = ? AND phone = ?", (investment_uid, phone)).fetchone()
        
        if not inv: raise HTTPException(status_code=404, detail="Investment not found")
        if inv['last_claimed_date'] == today: raise HTTPException(status_code=400, detail="Already claimed today")
        
        reward = inv['price'] * (inv['roi'] / 100)
        
        # Update Investment & User Balance
        conn.execute("UPDATE investments SET last_claimed_date = ? WHERE uid = ?", (today, investment_uid))
        conn.execute("UPDATE users SET balance = balance + ? WHERE phone = ?", (reward, phone))
        conn.execute("INSERT INTO transactions (phone, title, amount) VALUES (?, ?, ?)", (phone, f"Task Reward: {inv['plan_name']}", reward))
        
        conn.commit()
        return {"reward": reward}        
        
        
        

@app.get("/health")
async def health_check():
    return {"status": "alive"}

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)