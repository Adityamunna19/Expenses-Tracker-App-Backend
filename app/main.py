from __future__ import annotations

import csv
import logging
import os
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from app.database import get_connection, init_db
from app.schemas import (
    DashboardResponse,
    Expense,
    ExpenseCreate,
    ExpenseSummary,
    ExpenseUpdate,
    ParseExpenseRequest,
    ParsedExpense,
    ReceivableDashboardResponse,
    ReceivableReminder,
    ReceivableReminderCreate,
    ReceivableReminderReceive,
    SavingsDashboardResponse,
)
from app.services.parser import parse_expense_input


load_dotenv()
logger = logging.getLogger(__name__)


def get_allowed_origins() -> list[str]:
    raw_origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173")
    return [origin.strip().rstrip("/") for origin in raw_origins.split(",") if origin.strip()]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


app = FastAPI(title="Expenses Tracker API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/parse-expense", response_model=ParsedExpense)
def parse_expense(payload: ParseExpenseRequest) -> dict[str, object]:
    try:
        return parse_expense_input(payload.input)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/expenses", response_model=list[Expense])
def list_expenses(
    category: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    query = """
        SELECT
            id,
            amount,
            category,
            notes AS note,
            title,
            payment_method,
            expense_at,
            created_at
        FROM transactions
        WHERE status != 'ignored'
    """
    params: list[Any] = []
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY expense_at DESC, id DESC LIMIT ?"
    params.append(limit)

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


@app.get("/credits", response_model=list[Expense])
def list_credits(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                amount,
                category,
                notes AS note,
                title,
                payment_method,
                expense_at,
                created_at
            FROM transactions
            WHERE status != 'ignored' AND category = 'Credit'
            ORDER BY expense_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/expenses", response_model=Expense, status_code=201)
def create_expense(payload: ExpenseCreate) -> dict[str, Any]:
    logger.info("Create expense payload: %s", payload.model_dump(mode="json"))
    expense_at = (payload.expense_at or datetime.utcnow()).isoformat()
    title = payload.title or payload.note or payload.category

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO transactions (
                raw_message_id,
                source_type,
                title,
                amount,
                currency,
                category,
                payment_method,
                merchant_raw,
                merchant_clean,
                expense_at,
                notes,
                status,
                categorization_confidence,
                categorization_strategy,
                needs_review
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                "manual",
                title,
                payload.amount,
                "INR",
                payload.category,
                payload.payment_method,
                "",
                title,
                expense_at,
                payload.note,
                "confirmed",
                1.0,
                "manual",
                0,
            ),
        )
        expense_id = cursor.lastrowid
        row = connection.execute(
            """
            SELECT
                id,
                amount,
                category,
                notes AS note,
                title,
                payment_method,
                expense_at,
                created_at
            FROM transactions
            WHERE id = ?
            """,
            (expense_id,),
        ).fetchone()
    return dict(row)


@app.put("/expenses/{expense_id}", response_model=Expense)
def update_expense(expense_id: int, payload: ExpenseUpdate) -> dict[str, Any]:
    logger.info(
        "Update expense payload for id=%s: %s",
        expense_id,
        payload.model_dump(mode="json"),
    )
    title = payload.title or payload.note or payload.category
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM transactions WHERE id = ? AND status != 'ignored'",
            (expense_id,),
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Expense not found")

        connection.execute(
            """
            UPDATE transactions
            SET
                title = ?,
                amount = ?,
                category = ?,
                payment_method = ?,
                notes = ?,
                merchant_clean = ?,
                expense_at = ?,
                status = 'confirmed',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                title,
                payload.amount,
                payload.category,
                payload.payment_method,
                payload.note,
                title,
                payload.expense_at.isoformat(),
                expense_id,
            ),
        )
        row = connection.execute(
            """
            SELECT
                id,
                amount,
                category,
                notes AS note,
                title,
                payment_method,
                expense_at,
                created_at
            FROM transactions
            WHERE id = ?
            """,
            (expense_id,),
        ).fetchone()
    return dict(row)


def soft_delete_transaction(transaction_id: int) -> Response:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE transactions
            SET status = 'ignored', updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status != 'ignored'
            """,
            (transaction_id,),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Transaction not found")
    return Response(status_code=204)


@app.delete("/expenses/{expense_id}", status_code=204, response_class=Response)
def delete_expense(expense_id: int) -> Response:
    return soft_delete_transaction(expense_id)


@app.delete("/transactions/{transaction_id}", status_code=204, response_class=Response)
def delete_transaction(transaction_id: int) -> Response:
    return soft_delete_transaction(transaction_id)


@app.get("/expenses/summary", response_model=ExpenseSummary)
def get_summary(category: str | None = None) -> dict[str, Any]:
    query = """
        SELECT
            COUNT(*) AS total_count,
            COALESCE(SUM(amount), 0) AS total_amount
        FROM transactions
        WHERE status != 'ignored'
    """
    params: list[Any] = []
    if category:
        query += " AND category = ?"
        params.append(category)

    with get_connection() as connection:
        totals = connection.execute(query, params).fetchone()
    return dict(totals)


@app.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(category: str | None = None) -> dict[str, Any]:
    summary_query = """
        SELECT
            COUNT(*) AS total_count,
            COALESCE(SUM(amount), 0) AS total_amount
        FROM transactions
        WHERE status != 'ignored'
    """
    category_query = """
        SELECT
            category,
            COALESCE(SUM(amount), 0) AS total_amount,
            COUNT(*) AS total_count
        FROM transactions
        WHERE status != 'ignored'
    """
    summary_params: list[Any] = []
    category_params: list[Any] = []
    if category:
        summary_query += " AND category = ?"
        category_query += " AND category = ?"
        summary_params.append(category)
        category_params.append(category)
    category_query += """
        GROUP BY category
        ORDER BY total_amount DESC, category ASC
    """

    with get_connection() as connection:
        summary = connection.execute(summary_query, summary_params).fetchone()
        categories = connection.execute(category_query, category_params).fetchall()

    return {
        "summary": dict(summary),
        "categories": [dict(row) for row in categories],
    }


@app.get("/dashboard/savings", response_model=SavingsDashboardResponse)
def get_savings_dashboard(
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    with get_connection() as connection:
        summary = connection.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                COALESCE(SUM(amount), 0) AS total_amount
            FROM transactions
            WHERE status != 'ignored' AND category = 'Savings'
            """
        ).fetchone()
        rows = connection.execute(
            """
            SELECT
                id,
                amount,
                category,
                notes AS note,
                title,
                payment_method,
                expense_at,
                created_at
            FROM transactions
            WHERE status != 'ignored' AND category = 'Savings'
            ORDER BY expense_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return {
        "summary": dict(summary),
        "savings": [dict(row) for row in rows],
    }


@app.post("/receivables", response_model=ReceivableReminder, status_code=201)
def create_receivable(payload: ReceivableReminderCreate) -> dict[str, Any]:
    logger.info("Create receivable payload: %s", payload.model_dump(mode="json"))
    with get_connection() as connection:
        if payload.expense_id is not None:
            linked_expense = connection.execute(
                "SELECT id FROM transactions WHERE id = ? AND status != 'ignored'",
                (payload.expense_id,),
            ).fetchone()
            if linked_expense is None:
                raise HTTPException(status_code=404, detail="Linked expense not found")

        cursor = connection.execute(
            """
            INSERT INTO receivable_reminders (
                expense_id,
                title,
                amount,
                note,
                remind_at,
                status
            )
            VALUES (?, ?, ?, ?, ?, 'open')
            """,
            (
                payload.expense_id,
                payload.title,
                payload.amount,
                payload.note,
                payload.remind_at.isoformat(),
            ),
        )
        reminder_id = cursor.lastrowid
        row = connection.execute(
            """
            SELECT
                id,
                expense_id,
                title,
                amount,
                note,
                remind_at,
                status,
                received_transaction_id,
                received_at,
                created_at,
                updated_at
            FROM receivable_reminders
            WHERE id = ?
            """,
            (reminder_id,),
        ).fetchone()
    return dict(row)


@app.get("/receivables", response_model=list[ReceivableReminder])
def list_receivables(
    status: str = Query(default="open"),
    due_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    query = """
        SELECT
            id,
            expense_id,
            title,
            amount,
            note,
            remind_at,
            status,
            received_transaction_id,
            received_at,
            created_at,
            updated_at
        FROM receivable_reminders
        WHERE status = ?
    """
    params: list[Any] = [status]
    if due_only:
        query += " AND remind_at <= ?"
        params.append(utc_now().isoformat())
    query += " ORDER BY remind_at ASC, id DESC LIMIT ?"
    params.append(limit)

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


@app.get("/dashboard/receivables", response_model=ReceivableDashboardResponse)
def get_receivables_dashboard(
    due_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    query = """
        SELECT
            id,
            expense_id,
            title,
            amount,
            note,
            remind_at,
            status,
            received_transaction_id,
            received_at,
            created_at,
            updated_at
        FROM receivable_reminders
        WHERE status = 'open'
    """
    params: list[Any] = []
    if due_only:
        query += " AND remind_at <= ?"
        params.append(utc_now().isoformat())
    query += " ORDER BY remind_at ASC, id DESC LIMIT ?"
    params.append(limit)

    count_query = """
        SELECT COUNT(*) AS due_count
        FROM receivable_reminders
        WHERE status = 'open' AND remind_at <= ?
    """

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
        due_count_row = connection.execute(
            count_query,
            (utc_now().isoformat(),),
        ).fetchone()
        summary = connection.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                COALESCE(SUM(amount), 0) AS total_amount
            FROM receivable_reminders
            WHERE status = 'open'
            """
        ).fetchone()

    return {
        "summary": dict(summary),
        "due_count": int(due_count_row["due_count"]),
        "reminders": [dict(row) for row in rows],
    }


@app.patch("/receivables/{reminder_id}/receive", response_model=ReceivableReminder)
def mark_receivable_received(
    reminder_id: int,
    payload: ReceivableReminderReceive,
) -> dict[str, Any]:
    logger.info(
        "Receive receivable payload for id=%s: %s",
        reminder_id,
        payload.model_dump(mode="json"),
    )
    received_at = payload.received_at or utc_now()

    with get_connection() as connection:
        reminder = connection.execute(
            """
            SELECT id, title, amount, note, status
            FROM receivable_reminders
            WHERE id = ?
            """,
            (reminder_id,),
        ).fetchone()
        if reminder is None:
            raise HTTPException(status_code=404, detail="Receivable reminder not found")
        if reminder["status"] != "open":
            raise HTTPException(status_code=409, detail="Receivable reminder is already closed")

        credit_title = f"Received: {reminder['title']}"
        credit_note = payload.note or reminder["note"] or "Amount received back"
        credit_cursor = connection.execute(
            """
            INSERT INTO transactions (
                raw_message_id,
                source_type,
                title,
                amount,
                currency,
                category,
                payment_method,
                merchant_raw,
                merchant_clean,
                expense_at,
                notes,
                status,
                categorization_confidence,
                categorization_strategy,
                needs_review
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                "manual",
                credit_title,
                float(reminder["amount"]),
                "INR",
                "Credit",
                payload.payment_method,
                "",
                credit_title,
                received_at.isoformat(),
                credit_note,
                "confirmed",
                1.0,
                "manual",
                0,
            ),
        )
        received_transaction_id = credit_cursor.lastrowid

        connection.execute(
            """
            UPDATE receivable_reminders
            SET
                status = 'received',
                received_transaction_id = ?,
                received_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                received_transaction_id,
                received_at.isoformat(),
                reminder_id,
            ),
        )
        row = connection.execute(
            """
            SELECT
                id,
                expense_id,
                title,
                amount,
                note,
                remind_at,
                status,
                received_transaction_id,
                received_at,
                created_at,
                updated_at
            FROM receivable_reminders
            WHERE id = ?
            """,
            (reminder_id,),
        ).fetchone()
    return dict(row)


@app.get("/expenses/export")
def export_expenses_csv() -> StreamingResponse:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                title,
                amount,
                category,
                expense_at,
                notes,
                created_at
            FROM transactions
            WHERE status != 'ignored'
            ORDER BY expense_at DESC, id DESC
            """
        ).fetchall()

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "title", "amount", "category", "expense_at", "note", "created_at"])
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["title"],
                row["amount"],
                row["category"],
                row["expense_at"],
                row["notes"],
                row["created_at"],
            ]
        )

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=expenses.csv"},
    )
