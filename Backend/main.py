from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from database import supabase
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

# Updated CORS for Auth support
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELS ---
class Transaction(BaseModel):
    title: str
    amount: float
    type: str
    category: str
    payment_mode: str = "UPI"
    is_secret: bool = False
    sender: Optional[str] = None
    is_recovery: bool = False
    is_debt_payment: bool = False
    is_recovered: bool = False
    user_id: str  # Mandatory ownership field

class Goal(BaseModel):
    title: str
    target_amount: float
    current_amount: float = 0.0
    user_id: str # Mandatory ownership field

class GoalFund(BaseModel):
    amount_to_add: float

# --- HELPER: TIME TRAVEL FILTER ---
def filter_by_date(data, month, year):
    if not month or not year:
        return data
    prefix = f"{year}-{int(month):02d}"
    return [d for d in data if d.get('created_at', '').startswith(prefix)]

# --- TRANSACTIONS ROUTES ---
@app.get("/transactions")
async def get_transactions(x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing User ID")
    
    response = supabase.table("transactions").select("*")\
        .eq("user_id", x_user_id)\
        .order("created_at", desc=True).execute()
    return response.data

@app.post("/transactions")
async def add_transaction(transaction: Transaction):
    data = transaction.model_dump()
    response = supabase.table("transactions").insert(data).execute()
    return response.data[0]

@app.put("/transactions/{transaction_id}")
async def update_transaction(transaction_id: str, transaction: Transaction, x_user_id: str = Header(None)):
    data = transaction.model_dump()
    # Security: Ensure user only updates their own record
    response = supabase.table("transactions").update(data)\
        .eq("id", transaction_id)\
        .eq("user_id", x_user_id).execute()
    return response.data[0]

@app.delete("/transactions/{transaction_id}")
async def delete_transaction(transaction_id: str, x_user_id: str = Header(None)):
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
    return {"total_in": total_in, "total_out": total_out, "net": total_in - total_out}

@app.get("/analytics")
async def get_analytics(month: Optional[int] = None, year: Optional[int] = None, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)

    res = supabase.table("transactions").select("*")\
        .eq("type", "debit")\
        .eq("user_id", x_user_id).execute()
    
    data = filter_by_date(res.data, month, year)
    cat_data, mode_data = {}, {}
    
    for row in data:
        cat = row['category']
        cat_data[cat] = cat_data.get(cat, 0) + row['amount']
        pm = row.get('payment_mode', 'UPI')
        mode_data[pm] = mode_data.get(pm, 0) + row['amount']

    categories = sorted([{"name": k, "value": v} for k, v in cat_data.items()], key=lambda x: x['value'], reverse=True)
    modes = sorted([{"name": k, "value": v} for k, v in mode_data.items()], key=lambda x: x['value'], reverse=True)
    return {"categories": categories, "payment_modes": modes}

# --- SAVINGS GOALS ROUTES ---
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
    # Verify ownership before adding funds
    curr = supabase.table("savings_goals").select("current_amount")\
        .eq("id", goal_id)\
        .eq("user_id", x_user_id).execute()
    
    if not curr.data:
        raise HTTPException(status_code=404, detail="Goal not found or access denied")
        
    new_amount = curr.data[0]['current_amount'] + fund.amount_to_add
    res = supabase.table("savings_goals").update({"current_amount": new_amount})\
        .eq("id", goal_id)\
        .eq("user_id", x_user_id).execute()
    return res.data[0]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)