from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


PaymentMethod = str


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserProfile(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile


class ParseExpenseRequest(BaseModel):
    input: str = Field(min_length=1, max_length=200)

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Input cannot be empty")
        return cleaned


class ParsedExpense(BaseModel):
    amount: float = Field(gt=0)
    category: str
    note: str
    title: str
    confidence: float = Field(ge=0, le=1)
    strategy: str


class ExpenseCreate(BaseModel):
    amount: float = Field(gt=0)
    category: str = Field(min_length=1, max_length=50)
    note: str = Field(default="", max_length=500)
    title: str | None = Field(default=None, max_length=100)
    payment_method: PaymentMethod = Field(default="unknown", max_length=20)
    expense_at: datetime | None = None

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str) -> str:
        return value.strip()

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None

    @field_validator("payment_method")
    @classmethod
    def normalize_payment_method(cls, value: str) -> str:
        cleaned = value.strip().lower()
        allowed = {"upi", "card", "bank", "cash", "wallet", "unknown"}
        if cleaned not in allowed:
            raise ValueError("Unsupported payment method")
        return cleaned


class ExpenseUpdate(BaseModel):
    amount: float = Field(gt=0)
    category: str = Field(min_length=1, max_length=50)
    note: str = Field(default="", max_length=500)
    title: str | None = Field(default=None, max_length=100)
    payment_method: PaymentMethod = Field(default="unknown", max_length=20)
    expense_at: datetime

    @field_validator("payment_method")
    @classmethod
    def normalize_update_payment_method(cls, value: str) -> str:
        cleaned = value.strip().lower()
        allowed = {"upi", "card", "bank", "cash", "wallet", "unknown"}
        if cleaned not in allowed:
            raise ValueError("Unsupported payment method")
        return cleaned


class Expense(BaseModel):
    id: int
    amount: float
    category: str
    note: str
    title: str
    payment_method: str
    expense_at: datetime
    created_at: datetime


class ExpenseSummary(BaseModel):
    total_amount: float
    total_count: int


class CategoryBreakdownItem(BaseModel):
    category: str
    total_amount: float
    total_count: int


class DashboardResponse(BaseModel):
    summary: ExpenseSummary
    categories: list[CategoryBreakdownItem]


class SavingsDashboardResponse(BaseModel):
    summary: ExpenseSummary
    savings: list[Expense]


class ReceivableReminderCreate(BaseModel):
    amount: float = Field(gt=0)
    title: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=500)
    remind_at: datetime
    expense_id: int | None = None

    @field_validator("title")
    @classmethod
    def normalize_receivable_title(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("note")
    @classmethod
    def normalize_receivable_note(cls, value: str) -> str:
        return " ".join(value.split())


class ReceivableReminder(BaseModel):
    id: int
    expense_id: int | None
    title: str
    amount: float
    note: str
    remind_at: datetime
    status: str
    received_transaction_id: int | None
    received_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReceivableReminderReceive(BaseModel):
    payment_method: PaymentMethod = Field(default="unknown", max_length=20)
    received_at: datetime | None = None
    note: str = Field(default="", max_length=500)

    @field_validator("payment_method")
    @classmethod
    def normalize_receive_payment_method(cls, value: str) -> str:
        cleaned = value.strip().lower()
        allowed = {"upi", "card", "bank", "cash", "wallet", "unknown"}
        if cleaned not in allowed:
            raise ValueError("Unsupported payment method")
        return cleaned

    @field_validator("note")
    @classmethod
    def normalize_receive_note(cls, value: str) -> str:
        return " ".join(value.split())


class ReceivableDashboardResponse(BaseModel):
    summary: ExpenseSummary
    due_count: int
    reminders: list[ReceivableReminder]
