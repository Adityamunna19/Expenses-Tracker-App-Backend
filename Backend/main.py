from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database import supabase
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Transaction(BaseModel):
    title: str
    amount: float
    type: str
    category: str
    is_secret: bool = False
    sender: Optional[str] = None
    is_recovery: bool = False

@app.get("/transactions")
async def get_transactions():
    response = supabase.table("transactions").select("*").order("created_at", desc=True).execute()
    return response.data

@app.post("/transactions")
async def add_transaction(transaction: Transaction):
    data = transaction.model_dump()
    response = supabase.table("transactions").insert(data).execute()
    return response.data[0]

@app.put("/transactions/{transaction_id}")
async def update_transaction(transaction_id: str, transaction: Transaction):
    data = transaction.model_dump()
    response = supabase.table("transactions").update(data).eq("id", transaction_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return response.data[0]

@app.delete("/transactions/{transaction_id}")
async def delete_transaction(transaction_id: str):
    response = supabase.table("transactions").delete().eq("id", transaction_id).execute()
    # Supabase returns the deleted row in .data
    if not response.data:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "success"}

@app.get("/stats")
async def get_stats():
    res = supabase.table("transactions").select("amount, type").execute()
    total_in = sum(item['amount'] for item in res.data if item['type'] == 'credit')
    total_out = sum(item['amount'] for item in res.data if item['type'] == 'debit')
    return {"total_in": total_in, "total_out": total_out, "net": total_in - total_out}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)