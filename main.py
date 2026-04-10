import os
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv
from supabase import create_client, Client
from agents import smart_agent

# 1. Load Environment Variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
# Pull the hosted Vercel URL from .env; default to localhost for dev
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# 2. Initialize Supabase Client
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing Supabase credentials in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="Money Cockpit API")

# 3. Configure CORS (Security Gates)
origins = [
    "http://localhost:5173",
    FRONTEND_URL.rstrip("/"),  # Remove trailing slash if present
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Data Models
class Transaction(BaseModel):
    title: str
    amount: float
    type: str  # 'debit' or 'credit'
    category: str
    payment_mode: str = "UPI"
    is_secret: bool = False
    sender: Optional[str] = None
    is_recovery: bool = False
    is_debt_payment: bool = False
    is_recovered: bool = False
    user_id: str

class Goal(BaseModel):
    title: str
    target_amount: float
    current_amount: float = 0.0
    user_id: str
    image_url: Optional[str] = None

class GoalFund(BaseModel):
    amount_to_add: float

# 5. Helper Functions
def filter_by_date(data, month, year):
    if not month or not year:
        return data
    # Format: YYYY-MM
    prefix = f"{year}-{int(month):02d}"
    return [d for d in data if d.get('created_at', '').startswith(prefix)]

# 6. API Routes

@app.get("/")
async def health_check():
    return {"status": "online", "message": "Money Cockpit API is running"}

# --- TRANSACTION ROUTES ---
@app.get("/transactions")
async def get_transactions(x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    response = supabase.table("transactions").select("*")\
        .eq("user_id", x_user_id)\
        .order("created_at", desc=True).execute()
    return response.data

@app.post("/transactions")
async def add_transaction(transaction: Transaction):
    data = transaction.model_dump()
    response = supabase.table("transactions").insert(data).execute()
    return response.data[0]

@app.delete("/transactions/{transaction_id}")
async def delete_transaction(transaction_id: str, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    
    # Security: Only delete if user_id matches
    supabase.table("transactions").delete()\
        .eq("id", transaction_id)\
        .eq("user_id", x_user_id).execute()
    return {"status": "success"}

# --- ANALYTICS & STATS ---
@app.get("/stats")
async def get_stats(month: Optional[int] = None, year: Optional[int] = None, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    
    res = supabase.table("transactions").select("amount, type, created_at")\
        .eq("user_id", x_user_id).execute()
    
    data = filter_by_date(res.data, month, year)
    total_in = sum(item['amount'] for item in data if item['type'] == 'credit')
    total_out = sum(item['amount'] for item in data if item['type'] == 'debit')
    
    return {
        "total_in": total_in,
        "total_out": total_out,
        "net": total_in - total_out
    }

@app.get("/analytics")
async def get_analytics(month: Optional[int] = None, year: Optional[int] = None, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)

    res = supabase.table("transactions").select("*")\
        .eq("type", "debit")\
        .eq("user_id", x_user_id).execute()
    
    data = filter_by_date(res.data, month, year)
    cat_data = {}
    
    for row in data:
        cat = row['category']
        cat_data[cat] = cat_data.get(cat, 0) + row['amount']

    categories = sorted(
        [{"name": k, "value": v} for k, v in cat_data.items()],
        key=lambda x: x['value'],
        reverse=True
    )
    return {"categories": categories}

# --- SAVINGS GOALS ---
@app.get("/goals")
async def get_goals(x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    res = supabase.table("savings_goals").select("*")\
        .eq("user_id", x_user_id)\
        .order("created_at", desc=True).execute()
    return res.data

@app.post("/goals")
async def create_goal(goal: Goal):
    res = supabase.table("savings_goals").insert(goal.model_dump()).execute()
    return res.data[0]

@app.put("/goals/{goal_id}/add")
async def fund_goal(goal_id: str, fund: GoalFund, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
        
    curr = supabase.table("savings_goals").select("current_amount")\
        .eq("id", goal_id)\
        .eq("user_id", x_user_id).execute()
    
    if not curr.data:
        raise HTTPException(status_code=404, detail="Goal not found")
        
    new_amount = curr.data[0]['current_amount'] + fund.amount_to_add
    res = supabase.table("savings_goals").update({"current_amount": new_amount})\
        .eq("id", goal_id).execute()
    return res.data[0]

@app.delete("/goals/{goal_id}")
async def delete_goal(goal_id: str, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    
    # Security: Ensure only the owner can delete
    supabase.table("savings_goals").delete()\
        .eq("id", goal_id)\
        .eq("user_id", x_user_id).execute()
    return {"status": "success"}

@app.get("/goals/research")
async def research_goal(query: str):
    if not query:
        raise HTTPException(status_code=400, detail="What should I search for?")
    
    # Let the agent do the work
    result = smart_agent.fetch_product_data(query)
    
    if not result:
        raise HTTPException(status_code=500, detail="Agent couldn't find info.")
        
    return result

# 7. Execution Entry Point
if __name__ == "__main__":
    import uvicorn
    # Use environment PORT for Render deployment
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)