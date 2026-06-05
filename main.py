import os
import re
import json
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from supabase import create_client, Client
from agents import smart_agent, release_agent
from image_agent import image_agent
from scheduler import start_scheduler
from collections import defaultdict
from datetime import datetime, timedelta

# 1. Load Environment Variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing Supabase credentials in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = FastAPI(title="Money Cockpit API")

# 👇 THE MISSING DECORATOR IS ADDED HERE
@app.on_event("startup")
async def startup_event():
    # Wakes up the background worker when FastAPI starts
    start_scheduler(supabase)

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
    title: Optional[str] = None
    amount: float
    type: Optional[str] = None  # 'debit', 'credit', or 'transfer'
    category: Optional[str] = None
    user_id: Optional[str] = None
    
    payment_method: Optional[str] = "UPI"
    payment_mode: Optional[str] = None
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
    to_account_id: Optional[str] = None
    is_loan: bool = False
    loan_category: Optional[str] = None

class TransactionUpdate(BaseModel):
    title: Optional[str] = None
    amount: Optional[float] = None
    type: Optional[str] = None
    category: Optional[str] = None
    payment_method: Optional[str] = None
    date: Optional[str] = None
    note: Optional[str] = None
    is_secret: Optional[bool] = None
    is_recurring: Optional[bool] = None
    is_recovery: Optional[bool] = None
    is_debt_payment: Optional[bool] = None
    is_recovered: Optional[bool] = None
    goal_id: Optional[str] = None
    sender: Optional[str] = None
    expected_recovery_date: Optional[str] = None
    account_id: Optional[str] = None
    to_account_id: Optional[str] = None

class Goal(BaseModel):
    title: str
    target_amount: float
    current_amount: float = 0.0
    user_id: str
    image_url: Optional[str] = None

class GoalFund(BaseModel):
    amount_to_add: float

class CategoryModel(BaseModel):
    name: str
    type: Optional[str] = "expense"
    user_id: Optional[str] = None

class Note(BaseModel):
    title: Optional[str] = None
    content: str
    date: Optional[str] = None
    user_id: Optional[str] = None

class SmartParseRequest(BaseModel):
    text: str
    available_goals: List[Dict[str, Any]] = []
    merchant_aliases: Optional[Dict[str, str]] = None
    custom_categories: Optional[List[str]] = None

class Account(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None  
    is_primary: Optional[bool] = None
    user_id: Optional[str] = None
    credit_limit: Optional[float] = None
    balance: Optional[float] = 0.0

class ScreenshotRequest(BaseModel):
    image: str
    merchant_aliases: Optional[Dict[str, str]] = None

class BudgetInput(BaseModel):
    category: str
    monthly_limit: float    

class PushToken(BaseModel):
    token: str    

class CommitMessages(BaseModel):
    commits: List[str]

# 6. API Routes
@app.get("/")
async def health_check():
    return {"status": "online", "message": "Money Cockpit API is running"}

# --- SMART PARSE ROUTE ---
@app.post("/smart-parse")
async def smart_parse_endpoint(request: SmartParseRequest):
    result = smart_agent.parse_transaction_text(
        text=request.text, 
        available_goals=request.available_goals,
        merchant_aliases=request.merchant_aliases,
        custom_categories=request.custom_categories
    )
    return result

# --- SETTINGS / PUSH NOTIFICATIONS ---
@app.post("/settings/push-token")
async def save_push_token(payload: PushToken, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    try:
        existing = supabase.table("user_settings").select("user_id").eq("user_id", x_user_id).execute()
        if existing.data:
            supabase.table("user_settings").update({"push_token": payload.token}).eq("user_id", x_user_id).execute()
        else:
            supabase.table("user_settings").insert({
                "user_id": x_user_id,
                "push_token": payload.token,
                "reminders_enabled": True
            }).execute()
        return {"status": "success"}
    except Exception as e:
        print(f"Push Token Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save push token")

# --- TRANSACTION ROUTES ---
@app.post("/transactions/analyze-screenshot")
async def analyze_receipt(request: ScreenshotRequest):
    result = image_agent.analyze_screenshot(request.image, merchant_aliases=request.merchant_aliases)
    if not result:
        raise HTTPException(status_code=500, detail="AI Vision failed")
    return result

@app.get("/transactions")
async def get_transactions(month: Optional[int] = None, year: Optional[int] = None, x_user_id: str = Header(None)):
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
async def add_transaction(transaction: Transaction, x_user_id: str = Header(None)):
    data = transaction.model_dump()

    # Accept user id from header when frontend doesn't send it in payload.
    data["user_id"] = data.get("user_id") or x_user_id
    if not data["user_id"]:
        raise HTTPException(status_code=422, detail="user_id is required (body.user_id or x-user-id header)")

    # Backward compatibility for older frontend payload key.
    if data.get("payment_mode") and not data.get("payment_method"):
        data["payment_method"] = data["payment_mode"]
    data.pop("payment_mode", None)

    # Loan entries often omit generic fields; normalize them safely.
    if data.get("is_loan"):
        if not data.get("category"):
            data["category"] = data.get("loan_category") or "Loan"
        if not data.get("title"):
            data["title"] = "Loan Entry"
        if not data.get("type"):
            data["type"] = "debit"

    # Fallbacks for non-loan/partial payloads.
    data["title"] = (data.get("title") or "").strip() or "Transaction"
    data["type"] = data.get("type") or "debit"
    data["category"] = data.get("category") or "General"
    
    if data.get("expected_recovery_date") == "":
        data["expected_recovery_date"] = None
    
    if data.get("date") == "" or data.get("date") is None:
        from datetime import datetime
        data["date"] = datetime.now().strftime("%Y-%m-%d")

    if data.get('type') != 'transfer':
        data['to_account_id'] = None

    # These are app-level helper fields; avoid DB errors if columns do not exist.
    data.pop("is_loan", None)
    data.pop("loan_category", None)

    response = supabase.table("transactions").insert(data).execute()
    new_tx = response.data[0]
    
    # --- Account Balances & Loan / Savings Handlers ---
    try:
        if data.get("account_id"):
            acc_res = supabase.table("accounts").select("balance, type").eq("id", data["account_id"]).execute()
            if acc_res.data:
                current_bal = acc_res.data[0].get("balance") or 0.0
                new_bal = current_bal - data["amount"] if data["type"] == "debit" else current_bal + data["amount"]
                
                # If income is categorized as "Savings", it implies a withdrawal from the total savings balance
                if data["type"] == "credit" and data.get("category", "").lower() == "savings":
                    new_bal = current_bal - data["amount"]
                    
                supabase.table("accounts").update({"balance": new_bal}).eq("id", data["account_id"]).execute()

        if data.get("to_account_id"):
            to_acc_res = supabase.table("accounts").select("balance, type").eq("id", data["to_account_id"]).execute()
            if to_acc_res.data:
                to_current_bal = to_acc_res.data[0].get("balance") or 0.0
                acc_type = to_acc_res.data[0].get("type") or ""
                
                # If transferring TO a loan account, reduce the debt balance
                new_to_bal = to_current_bal - data["amount"] if acc_type.lower() == "loan" else to_current_bal + data["amount"]
                supabase.table("accounts").update({"balance": new_to_bal}).eq("id", data["to_account_id"]).execute()
    except Exception as e:
        print(f"Failed to update account balances: {e}")

    return new_tx

@app.put("/transactions/{transaction_id}")
@app.patch("/transactions/{transaction_id}")
async def update_transaction(transaction_id: str, payload: TransactionUpdate, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    # Keep stored null semantics consistent with create flow.
    if update_data.get("expected_recovery_date") == "":
        update_data["expected_recovery_date"] = None
    if update_data.get("date") == "":
        update_data["date"] = None

    # Non-transfer rows should not carry destination account.
    if update_data.get("type") and update_data["type"] != "transfer":
        update_data["to_account_id"] = None

    # Defensive cleanup in case frontend sends non-schema helper fields.
    update_data.pop("is_loan", None)
    update_data.pop("loan_category", None)

    try:
        existing = (
            supabase.table("transactions")
            .select("id")
            .eq("id", transaction_id)
            .eq("user_id", x_user_id)
            .limit(1)
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Transaction not found")

        res = (
            supabase.table("transactions")
            .update(update_data)
            .eq("id", transaction_id)
            .eq("user_id", x_user_id)
            .execute()
        )
        return res.data[0] if res.data else {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/transactions/{transaction_id}")
async def delete_transaction(transaction_id: str, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    supabase.table("transactions").delete().eq("id", transaction_id).eq("user_id", x_user_id).execute()
    return {"status": "success"}

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
        # 👇 The correct duplicate block that stops the 500 error!
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

@app.put("/accounts/{account_id}/limit")
async def update_card_limit(account_id: str, limit: float, x_user_id: str = Header(None)):
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

# --- ANALYTICS & STATS ---
@app.get("/stats")
async def get_stats(month: Optional[int] = None, year: Optional[int] = None, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    
    query = supabase.table("transactions").select("amount, type, category").eq("user_id", x_user_id)
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
    total_out = sum(item['amount'] for item in data if item['type'] == 'debit' or item.get('category', '').lower() == 'credit card')
    return {"total_in": total_in, "total_out": total_out, "net": total_in - total_out}

@app.get("/analytics")
async def get_analytics(month: Optional[int] = None, year: Optional[int] = None, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
        
    query = supabase.table("transactions").select("amount, category, type").eq("user_id", x_user_id)
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
        if row['type'] == 'debit' or row.get('category', '').lower() == 'credit card':
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
    
@app.get("/subscriptions")
async def get_subscriptions(x_user_id: str = Header(None)):
    """Detects recurring monthly subscriptions based on transaction history patterns."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        # 1. Fetch the last 6 months of debits to find patterns
        six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        res = supabase.table("transactions") \
            .select("title, amount, date") \
            .eq("type", "debit") \
            .eq("user_id", x_user_id) \
            .gte("date", six_months_ago) \
            .order("date", desc=False) \
            .execute()
            
        transactions = res.data or []
        
        # 2. Group transactions by Merchant (ignoring case)
        merchant_groups = defaultdict(list)
        for tx in transactions:
            merchant = tx['title'].strip().lower()
            merchant_groups[merchant].append(tx)
            
        subscriptions = []
        monthly_burn = 0
        now = datetime.now()
        
        # 3. Analyze each merchant for subscription patterns
        for merchant, txs in merchant_groups.items():
            if len(txs) >= 2: # Need at least 2 payments to establish a pattern
                dates = [datetime.strptime(t['date'], "%Y-%m-%d") for t in txs]
                intervals = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
                
                # Check if the average time between payments is roughly a month
                avg_interval = sum(intervals) / len(intervals)
                if 25 <= avg_interval <= 35:
                    
                    # Check if the amounts are similar (allowing a 20% variance for taxes/proration)
                    latest_amount = txs[-1]['amount']
                    if all(abs(t['amount'] - latest_amount) / latest_amount <= 0.20 for t in txs):
                        
                        # Calculate when they will charge you next
                        next_due = dates[-1] + timedelta(days=round(avg_interval))
                        
                        # Only include it if it's currently active (hasn't been cancelled months ago)
                        if next_due >= now - timedelta(days=15):
                            subscriptions.append({
                                "id": f"sub_{merchant}",
                                "merchant": txs[-1]['title'], # Use original casing
                                "amount": latest_amount,
                                "next_due_date": next_due.strftime("%Y-%m-%d"),
                                "frequency": f"Every ~{round(avg_interval)} days",
                                "history_count": len(txs)
                            })
                            monthly_burn += latest_amount
                            
        # 4. Sort by what is due next
        subscriptions.sort(key=lambda x: x['next_due_date'])
        
        return {
            "status": "success",
            "monthly_burn": monthly_burn,
            "subscriptions": subscriptions
        }
        
    except Exception as e:
        print(f"Subscription Engine Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze subscriptions")    

# --- CUSTOM CATEGORIES ---
@app.get("/categories")
async def get_categories(x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    res = supabase.table("categories").select("*").eq("user_id", x_user_id).execute()
    return res.data

@app.post("/categories")
async def create_category(category: CategoryModel, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    data = category.model_dump(exclude_unset=True)
    data["user_id"] = x_user_id
    res = supabase.table("categories").insert(data).execute()
    return res.data[0] if res.data else {"status": "success"}

@app.delete("/categories/{category_id}")
async def delete_category(category_id: str, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    supabase.table("categories").delete().eq("id", category_id).eq("user_id", x_user_id).execute()
    return {"status": "success"}

# --- PERSONAL DIARY (NOTES) ---
@app.get("/notes")
async def get_notes(x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    res = supabase.table("notes").select("*").eq("user_id", x_user_id).order("created_at", desc=True).execute()
    return res.data

@app.post("/notes")
async def create_note(note: Note, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    data = note.model_dump(exclude_unset=True)
    data["user_id"] = x_user_id
    if not data.get("date"):
        data["date"] = datetime.now().strftime("%Y-%m-%d")
    res = supabase.table("notes").insert(data).execute()
    return res.data[0] if res.data else {"status": "success"}

@app.delete("/notes/{note_id}")
async def delete_note(note_id: str, x_user_id: str = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401)
    supabase.table("notes").delete().eq("id", note_id).eq("user_id", x_user_id).execute()
    return {"status": "success"}

# --- ANNOUNCEMENTS / RELEASE NOTES ---
@app.post("/admin/announcements/generate")
async def generate_and_publish_announcement(payload: CommitMessages, x_admin_key: str = Header(None)):
    # Optional: You can check `x_admin_key` against an environment variable to secure this route
    announcement_data = release_agent.generate_release_notes(payload.commits)
    
    if not announcement_data:
        raise HTTPException(status_code=500, detail="Failed to generate release notes via AI")
        
    title_str = announcement_data.get("title", "New Update")
    slug = re.sub(r'[^a-z0-9]+', '-', title_str.lower()).strip('-')

    # We map the JSON result into the `content` field so it fits the existing `announcements` table
    insert_data = {
        "title": title_str,
        "content": json.dumps({
            "summary": announcement_data.get("summary"),
            "highlights": announcement_data.get("highlights"),
            "cta_label": announcement_data.get("cta_label"),
            "cta_subtext": announcement_data.get("cta_subtext")
        }),
        "version_tag": slug,
        "is_active": True
    }
    
    res = supabase.table("announcements").insert(insert_data).execute()
    return res.data[0] if res.data else {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
