import os
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from supabase import create_client, Client
from agents import smart_agent
from image_agent import image_agent

# 1. Load Environment Variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing Supabase credentials in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = FastAPI(title="Money Cockpit API")

# 3. Configure CORS
origins = [
    "http://localhost:5173",
    FRONTEND_URL.rstrip("/"),
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Data Models (Updated to match your new UI)
class Transaction(BaseModel):
    title: str
    amount: float
    type: str  # 'debit' or 'credit'
    category: str
    user_id: str
    
    # Optional fields to match your new UI
    payment_method: Optional[str] = "UPI"
    date: Optional[str] = None
    note: Optional[str] = ""
    is_secret: Optional[bool] = False
    is_recurring: Optional[bool] = False
    is_recovery: Optional[bool] = False
    is_debt_payment: Optional[bool] = False
    is_recovered: Optional[bool] = False
    goal_id: Optional[str] = None
    sender: Optional[str] = None
    is_recovered: Optional[bool] = False
    expected_recovery_date: Optional[str] = None
    account_id: Optional[str] = None

class Goal(BaseModel):
    title: str
    target_amount: float
    current_amount: float = 0.0
    user_id: str
    image_url: Optional[str] = None

class GoalFund(BaseModel):
    amount_to_add: float

class SmartParseRequest(BaseModel):
    text: str
    available_goals: List[Dict[str, Any]] = []

class Account(BaseModel):
    name: str
    type: str  # 'bank' or 'card'
    is_primary: bool = False
    user_id: str    

class ScreenshotRequest(BaseModel):
    image: str
    

# 5. Helper Functions
def filter_by_date(data, month, year):
    if not month or not year:
        return data
    prefix = f"{year}-{int(month):02d}"
    return [d for d in data if d.get('created_at', '').startswith(prefix)]

# 6. API Routes
@app.get("/")
async def health_check():
    return {"status": "online", "message": "Money Cockpit API is running"}

# --- NEW: SMART PARSE ROUTE ---
@app.post("/smart-parse")
async def smart_parse_endpoint(request: SmartParseRequest):
    result = smart_agent.parse_transaction_text(request.text, request.available_goals)
    return result

# --- TRANSACTION ROUTES ---
@app.post("/transactions/analyze-screenshot")
async def analyze_receipt(request: ScreenshotRequest):
    result = image_agent.analyze_screenshot(request.image)
    if not result:
        raise HTTPException(status_code=500, detail="AI Vision failed")
    return result

@app.get("/transactions")
async def get_transactions(x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    response = supabase.table("transactions").select("*").eq("user_id", x_user_id).order("created_at", desc=True).execute()
    return response.data

@app.post("/transactions")
async def add_transaction(transaction: Transaction):
    data = transaction.model_dump()
    
    # --- FIX: Clean up date fields to prevent "invalid input syntax" ---
    if data.get("expected_recovery_date") == "":
        data["expected_recovery_date"] = None
    
    if data.get("date") == "":
        # If the main transaction date is missing, default to today
        from datetime import datetime
        data["date"] = datetime.now().strftime("%Y-%m-%d")

    response = supabase.table("transactions").insert(data).execute()
    return response.data[0]

@app.delete("/transactions/{transaction_id}")
async def delete_transaction(transaction_id: str, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    supabase.table("transactions").delete().eq("id", transaction_id).eq("user_id", x_user_id).execute()
    return {"status": "success"}

# --- ANALYTICS & STATS ---
@app.get("/stats")
async def get_stats(month: Optional[int] = None, year: Optional[int] = None, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    res = supabase.table("transactions").select("amount, type, created_at").eq("user_id", x_user_id).execute()
    data = filter_by_date(res.data, month, year)
    total_in = sum(item['amount'] for item in data if item['type'] == 'credit')
    total_out = sum(item['amount'] for item in data if item['type'] == 'debit')
    return {"total_in": total_in, "total_out": total_out, "net": total_in - total_out}

@app.get("/analytics")
async def get_analytics(month: Optional[int] = None, year: Optional[int] = None, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    res = supabase.table("transactions").select("*").eq("type", "debit").eq("user_id", x_user_id).execute()
    data = filter_by_date(res.data, month, year)
    cat_data = {}
    for row in data:
        cat = row['category']
        cat_data[cat] = cat_data.get(cat, 0) + row['amount']
    categories = sorted([{"name": k, "value": v} for k, v in cat_data.items()], key=lambda x: x['value'], reverse=True)
    return {"categories": categories}

# --- SAVINGS GOALS (Fixed to query 'goals' instead of 'savings_goals') ---
@app.get("/goals")
async def get_goals(x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    res = supabase.table("goals").select("*").eq("user_id", x_user_id).order("created_at", desc=True).execute()
    return res.data

@app.post("/goals")
async def create_goal(goal: Goal):
    res = supabase.table("goals").insert(goal.model_dump()).execute()
    return res.data[0]

@app.put("/goals/{goal_id}/add")
async def fund_goal(goal_id: str, fund: GoalFund, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    curr = supabase.table("goals").select("current_amount").eq("id", goal_id).eq("user_id", x_user_id).execute()
    if not curr.data:
        raise HTTPException(status_code=404, detail="Goal not found")
    new_amount = curr.data[0]['current_amount'] + fund.amount_to_add
    res = supabase.table("goals").update({"current_amount": new_amount}).eq("id", goal_id).execute()
    return res.data[0]

@app.put("/transactions/{transaction_id}/resolve-recovery")
async def resolve_recovery(transaction_id: str, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
        
    try:
        # 1. Mark original expense as recovered
        supabase.table("transactions").update({"is_recovered": True}).eq("id", transaction_id).eq("user_id", x_user_id).execute()
        
        # 2. Fetch the original transaction details to duplicate as Income
        orig_res = supabase.table("transactions").select("*").eq("id", transaction_id).execute()
        if not orig_res.data:
            raise HTTPException(status_code=404, detail="Transaction not found")
            
        orig = orig_res.data[0]
        
        # 3. Create the automated Income (Credit) transaction
        income_data = {
            "title": f"Recovery from: {orig['title']}",
            "amount": orig['amount'],
            "category": "Refund",
            "type": "credit",
            "payment_method": "Bank Transfer", # Default
            "user_id": x_user_id,
            "is_recovered": True # Mark this linking transaction as true as well
        }
        supabase.table("transactions").insert(income_data).execute()
        
        return {"status": "success", "message": "Recovery resolved and Income added!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/goals/{goal_id}")
async def delete_goal(goal_id: str, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    supabase.table("goals").delete().eq("id", goal_id).eq("user_id", x_user_id).execute()
    return {"status": "success"}

@app.get("/goals/research")
async def research_goal(query: str):
    if not query:
        raise HTTPException(status_code=400, detail="What should I search for?")
    result = smart_agent.fetch_product_data(query)
    if not result:
        raise HTTPException(status_code=500, detail="Agent couldn't find info.")
    return result

@app.get("/accounts")
async def get_accounts(x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    res = supabase.table("accounts").select("*").eq("user_id", x_user_id).order("created_at").execute()
    return res.data

@app.post("/accounts")
async def create_account(account: Account):
    data = account.model_dump()
    res = supabase.table("accounts").insert(data).execute()
    return res.data[0]

@app.delete("/accounts/{account_id}")
async def delete_account(account_id: str, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    
    # Delete the account (only if it belongs to this user)
    supabase.table("accounts").delete().eq("id", account_id).eq("user_id", x_user_id).execute()
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)