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

# 4. Data Models
class Transaction(BaseModel):
    title: str
    amount: float
    type: str  # 'debit', 'credit', or 'transfer'
    category: str
    user_id: str
    
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
    expected_recovery_date: Optional[str] = None
    account_id: Optional[str] = None
    to_account_id: Optional[str] = None # 👈 CRITICAL: Added for Credit Card Bill Payments

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
    name: Optional[str] = None
    type: Optional[str] = None  # 'bank' or 'card'
    is_primary: Optional[bool] = None
    user_id: Optional[str] = None
    credit_limit: Optional[float] = None

class ScreenshotRequest(BaseModel):
    image: str

class BudgetInput(BaseModel):
    category: str
    monthly_limit: float    

# 6. API Routes
@app.get("/")
async def health_check():
    return {"status": "online", "message": "Money Cockpit API is running"}

# --- SMART PARSE ROUTE ---
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
async def get_transactions(month: Optional[int] = None, year: Optional[int] = None, x_user_id: str = Header(None)):
    """FIXED: Now properly filters transactions by the selected month/year."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    query = supabase.table("transactions").select("*").eq("user_id", x_user_id)

    if month and year:
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            next_month_start = f"{year + 1}-01-01"
        else:
            next_month_start = f"{year}-{month + 1:02d}-01"
            
        query = query.gte("date", start_date).lt("date", next_month_start)

    response = query.order("date", desc=True).execute()
    return response.data

@app.post("/transactions")
async def add_transaction(transaction: Transaction):
    data = transaction.model_dump()
    
    if data.get("expected_recovery_date") == "":
        data["expected_recovery_date"] = None
    
    if data.get("date") == "" or data.get("date") is None:
        from datetime import datetime
        data["date"] = datetime.now().strftime("%Y-%m-%d")

    # Security check: If it's not a transfer, force to_account_id to None
    if data.get('type') != 'transfer':
        data['to_account_id'] = None

    response = supabase.table("transactions").insert(data).execute()
    return response.data[0]

@app.put("/accounts/{account_id}")
async def update_account(account_id: str, account: Account, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        # 👇 ADDED exclude_none=True to prevent database crashes!
        update_data = {
            k: v for k, v in account.model_dump(exclude_none=True).items() 
            if k not in ["id", "user_id", "created_at"]
        }
        
        existing = supabase.table("accounts").select("id").eq("id", account_id).eq("user_id", x_user_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Account not found")
            
        res = supabase.table("accounts").update(update_data).eq("id", account_id).eq("user_id", x_user_id).execute()
        return {"status": "success", "message": "Account updated", "data": res.data[0] if res.data else None}
    except Exception as e:
        print(f"Update Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update account")

@app.delete("/transactions/{transaction_id}")
async def delete_transaction(transaction_id: str, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    supabase.table("transactions").delete().eq("id", transaction_id).eq("user_id", x_user_id).execute()
    return {"status": "success"}

# --- ANALYTICS & STATS (Fixed Filtering Logic) ---
@app.get("/stats")
async def get_stats(month: Optional[int] = None, year: Optional[int] = None, x_user_id: str = Header(None)):
    """FIXED: Uses robust SQL date range filtering."""
    if not x_user_id:
        raise HTTPException(status_code=401)
    
    query = supabase.table("transactions").select("amount, type").eq("user_id", x_user_id)
    
    if month and year:
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            next_month_start = f"{year + 1}-01-01"
        else:
            next_month_start = f"{year}-{month + 1:02d}-01"
        query = query.gte("date", start_date).lt("date", next_month_start)

    res = query.execute()
    data = res.data or []
    
    total_in = sum(item['amount'] for item in data if item['type'] == 'credit')
    total_out = sum(item['amount'] for item in data if item['type'] == 'debit')
    return {"total_in": total_in, "total_out": total_out, "net": total_in - total_out}

@app.get("/analytics")
async def get_analytics(month: Optional[int] = None, year: Optional[int] = None, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
        
    query = supabase.table("transactions").select("amount, category").eq("type", "debit").eq("user_id", x_user_id)
    
    if month and year:
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            next_month_start = f"{year + 1}-01-01"
        else:
            next_month_start = f"{year}-{month + 1:02d}-01"
        query = query.gte("date", start_date).lt("date", next_month_start)

    res = query.execute()
    data = res.data or []
    
    cat_data = {}
    for row in data:
        cat = row['category']
        cat_data[cat] = cat_data.get(cat, 0) + row['amount']
    categories = sorted([{"name": k, "value": v} for k, v in cat_data.items()], key=lambda x: x['value'], reverse=True)
    return {"categories": categories}

# --- SAVINGS GOALS ---
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

# --- RECOVERIES ---
@app.put("/transactions/{transaction_id}/resolve-recovery")
async def resolve_recovery(transaction_id: str, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    try:
        supabase.table("transactions").update({"is_recovered": True}).eq("id", transaction_id).eq("user_id", x_user_id).execute()
        orig_res = supabase.table("transactions").select("*").eq("id", transaction_id).execute()
        if not orig_res.data:
            raise HTTPException(status_code=404, detail="Transaction not found")
        orig = orig_res.data[0]
        income_data = {
            "title": f"Recovery from: {orig['title']}",
            "amount": orig['amount'],
            "category": "Refund",
            "type": "credit",
            "payment_method": "Bank Transfer", 
            "user_id": x_user_id,
            "is_recovered": True 
        }
        supabase.table("transactions").insert(income_data).execute()
        return {"status": "success", "message": "Recovery resolved and Income added!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- ACCOUNTS & CARDS ---
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

@app.put("/accounts/{account_id}")
async def update_account(account_id: str, account: Account, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        update_data = {k: v for k, v in account.model_dump().items() if k not in ["id", "user_id", "created_at"]}
        existing = supabase.table("accounts").select("id").eq("id", account_id).eq("user_id", x_user_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Account not found")
        res = supabase.table("accounts").update(update_data).eq("id", account_id).eq("user_id", x_user_id).execute()
        return {"status": "success", "message": "Account updated", "data": res.data[0] if res.data else None}
    except Exception as e:
        print(f"Update Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update account")

@app.put("/accounts/{account_id}/limit")
async def update_card_limit(account_id: str, limit: float, x_user_id: str = Header(None)):
    """NEW: Specific endpoint for updating Credit Card limits."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        res = supabase.table("accounts").update({"credit_limit": limit}).eq("id", account_id).eq("user_id", x_user_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"status": "success", "data": res.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/accounts/{account_id}")
async def delete_account(account_id: str, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    supabase.table("accounts").delete().eq("id", account_id).eq("user_id", x_user_id).execute()
    return {"status": "success"}

# --- BUDGETS ---
@app.get("/budgets")
async def get_budgets(x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized: User ID missing")
    try:
        response = supabase.table("budgets").select("*").eq("user_id", x_user_id).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching budgets: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")

@app.post("/budgets")
async def upsert_budget(budget: BudgetInput, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        existing = supabase.table("budgets").select("id").eq("user_id", x_user_id).eq("category", budget.category).execute()
        if existing.data:
            supabase.table("budgets").update({"monthly_limit": budget.monthly_limit}).eq("id", existing.data[0]["id"]).execute()
        else:
            supabase.table("budgets").insert({"user_id": x_user_id, "category": budget.category, "monthly_limit": budget.monthly_limit}).execute()
        return {"status": "success", "message": "Budget locked in"}
    except Exception as e:
        print(f"Budget Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save budget")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)