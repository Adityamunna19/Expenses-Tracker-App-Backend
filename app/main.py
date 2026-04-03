from __future__ import annotations

import csv
import logging
import os
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from app.database import get_connection, init_db
from app.schemas import (
    AuthTokenResponse,
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
    UserLogin,
    UserProfile,
    UserRegister,
)
from app.services.auth import (
    build_session_expiry,
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.services.parser import parse_expense_input


load_dotenv()
logger = logging.getLogger(__name__)


def get_allowed_origins() -> list[str]:
    raw_origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173")
    return [origin.strip().rstrip("/") for origin in raw_origins.split(",") if origin.strip()]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")
    return token


def get_current_user(token: str = Depends(get_bearer_token)) -> dict[str, Any]:
    token_hash = hash_session_token(token)
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT u.id, u.email, u.created_at, s.id AS session_id, s.expires_at
            FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= utc_now():
            connection.execute("DELETE FROM auth_sessions WHERE id = ?", (row["session_id"],))
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return {
        "id": row["id"],
        "email": row["email"],
        "created_at": row["created_at"],
    }


def serialize_user(row: dict[str, Any] | Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "created_at": row["created_at"],
    }


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


@app.post("/auth/register", response_model=AuthTokenResponse, status_code=201)
def register(payload: UserRegister) -> dict[str, Any]:
    normalized_email = payload.email.lower()
    password_hash = hash_password(payload.password)
    session_token = generate_session_token()
    expires_at = build_session_expiry()

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Email is already registered")

        cursor = connection.execute(
            """
            INSERT INTO users (email, password_hash)
            VALUES (?, ?)
            """,
            (normalized_email, password_hash),
        )
        user_id = cursor.lastrowid
        connection.execute(
            """
            INSERT INTO auth_sessions (user_id, token_hash, expires_at)
            VALUES (?, ?, ?)
            """,
            (user_id, hash_session_token(session_token), expires_at.isoformat()),
        )
        user = connection.execute(
            "SELECT id, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    return {
        "access_token": session_token,
        "token_type": "bearer",
        "user": serialize_user(user),
    }


@app.post("/auth/login", response_model=AuthTokenResponse)
def login(payload: UserLogin) -> dict[str, Any]:
    normalized_email = payload.email.lower()
    session_token = generate_session_token()
    expires_at = build_session_expiry()

    with get_connection() as connection:
        user = connection.execute(
            "SELECT id, email, password_hash, created_at FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()
        if user is None or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        connection.execute(
            """
            INSERT INTO auth_sessions (user_id, token_hash, expires_at)
            VALUES (?, ?, ?)
            """,
            (user["id"], hash_session_token(session_token), expires_at.isoformat()),
        )

    return {
        "access_token": session_token,
        "token_type": "bearer",
        "user": serialize_user(user),
    }


@app.get("/auth/me", response_model=UserProfile)
def get_me(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return current_user


@app.post("/auth/logout", status_code=204, response_class=Response)
def logout(token: str = Depends(get_bearer_token)) -> Response:
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM auth_sessions WHERE token_hash = ?",
            (hash_session_token(token),),
        )
    return Response(status_code=204)


@app.post("/parse-expense", response_model=ParsedExpense)
def parse_expense(
    payload: ParseExpenseRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, object]:
    try:
        return parse_expense_input(payload.input)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/expenses", response_model=list[Expense])
def list_expenses(
    category: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_current_user),
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
        WHERE status != 'ignored' AND user_id = ?
    """
    params: list[Any] = [current_user["id"]]
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY expense_at DESC, id DESC LIMIT ?"
    params.append(limit)

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


@app.get("/credits", response_model=list[Expense])
def list_credits(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
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
            WHERE status != 'ignored' AND category = 'Credit' AND user_id = ?
            ORDER BY expense_at DESC, id DESC
            LIMIT ?
            """,
            (current_user["id"], limit),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/expenses", response_model=Expense, status_code=201)
def create_expense(
    payload: ExpenseCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    logger.info("Create expense payload: %s", payload.model_dump(mode="json"))
    expense_at = (payload.expense_at or datetime.utcnow()).isoformat()
    title = payload.title or payload.note or payload.category

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO transactions (
                raw_message_id,
                user_id,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                current_user["id"],
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
def update_expense(
    expense_id: int,
    payload: ExpenseUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    logger.info(
        "Update expense payload for id=%s: %s",
        expense_id,
        payload.model_dump(mode="json"),
    )
    title = payload.title or payload.note or payload.category
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM transactions WHERE id = ? AND status != 'ignored' AND user_id = ?",
            (expense_id, current_user["id"]),
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


def soft_delete_transaction(transaction_id: int, user_id: int) -> Response:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE transactions
            SET status = 'ignored', updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status != 'ignored' AND user_id = ?
            """,
            (transaction_id, user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Transaction not found")
    return Response(status_code=204)


@app.delete("/expenses/{expense_id}", status_code=204, response_class=Response)
def delete_expense(
    expense_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> Response:
    return soft_delete_transaction(expense_id, current_user["id"])


@app.delete("/transactions/{transaction_id}", status_code=204, response_class=Response)
def delete_transaction(
    transaction_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> Response:
    return soft_delete_transaction(transaction_id, current_user["id"])


@app.get("/expenses/summary", response_model=ExpenseSummary)
def get_summary(
    category: str | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    query = """
        SELECT
            COUNT(*) AS total_count,
            COALESCE(SUM(amount), 0) AS total_amount
        FROM transactions
        WHERE status != 'ignored' AND user_id = ?
    """
    params: list[Any] = [current_user["id"]]
    if category:
        query += " AND category = ?"
        params.append(category)

    with get_connection() as connection:
        totals = connection.execute(query, params).fetchone()
    return dict(totals)


@app.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    category: str | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    summary_query = """
        SELECT
            COUNT(*) AS total_count,
            COALESCE(SUM(amount), 0) AS total_amount
        FROM transactions
        WHERE status != 'ignored' AND user_id = ?
    """
    category_query = """
        SELECT
            category,
            COALESCE(SUM(amount), 0) AS total_amount,
            COUNT(*) AS total_count
        FROM transactions
        WHERE status != 'ignored' AND user_id = ?
    """
    summary_params: list[Any] = [current_user["id"]]
    category_params: list[Any] = [current_user["id"]]
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
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    with get_connection() as connection:
        summary = connection.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                COALESCE(SUM(amount), 0) AS total_amount
            FROM transactions
            WHERE status != 'ignored' AND category = 'Savings' AND user_id = ?
            """,
            (current_user["id"],),
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
            WHERE status != 'ignored' AND category = 'Savings' AND user_id = ?
            ORDER BY expense_at DESC, id DESC
            LIMIT ?
            """,
            (current_user["id"], limit),
        ).fetchall()

    return {
        "summary": dict(summary),
        "savings": [dict(row) for row in rows],
    }


@app.post("/receivables", response_model=ReceivableReminder, status_code=201)
def create_receivable(
    payload: ReceivableReminderCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    logger.info("Create receivable payload: %s", payload.model_dump(mode="json"))
    with get_connection() as connection:
        if payload.expense_id is not None:
            linked_expense = connection.execute(
                "SELECT id FROM transactions WHERE id = ? AND status != 'ignored' AND user_id = ?",
                (payload.expense_id, current_user["id"]),
            ).fetchone()
            if linked_expense is None:
                raise HTTPException(status_code=404, detail="Linked expense not found")

        cursor = connection.execute(
            """
            INSERT INTO receivable_reminders (
                expense_id,
                user_id,
                title,
                amount,
                note,
                remind_at,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'open')
            """,
            (
                payload.expense_id,
                current_user["id"],
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
    current_user: dict[str, Any] = Depends(get_current_user),
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
        WHERE status = ? AND user_id = ?
    """
    params: list[Any] = [status, current_user["id"]]
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
    current_user: dict[str, Any] = Depends(get_current_user),
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
        WHERE status = 'open' AND user_id = ?
    """
    params: list[Any] = [current_user["id"]]
    if due_only:
        query += " AND remind_at <= ?"
        params.append(utc_now().isoformat())
    query += " ORDER BY remind_at ASC, id DESC LIMIT ?"
    params.append(limit)

    count_query = """
        SELECT COUNT(*) AS due_count
        FROM receivable_reminders
        WHERE status = 'open' AND user_id = ? AND remind_at <= ?
    """

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
        due_count_row = connection.execute(
            count_query,
            (current_user["id"], utc_now().isoformat()),
        ).fetchone()
        summary = connection.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                COALESCE(SUM(amount), 0) AS total_amount
            FROM receivable_reminders
            WHERE status = 'open' AND user_id = ?
            """,
            (current_user["id"],),
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
    current_user: dict[str, Any] = Depends(get_current_user),
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
            WHERE id = ? AND user_id = ?
            """,
            (reminder_id, current_user["id"]),
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
                user_id,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                current_user["id"],
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
