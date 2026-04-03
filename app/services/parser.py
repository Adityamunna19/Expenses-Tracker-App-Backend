from __future__ import annotations

import re

from app.services.categorizer import categorize_text


AMOUNT_PATTERN = re.compile(
    r"(?<!\w)(?:rs\.?|inr|₹)?\s*(\d+(?:[.,]\d{1,2})?)(?!\w)",
    re.IGNORECASE,
)
FILLER_WORDS = {
    "spent",
    "pay",
    "paid",
    "for",
    "on",
    "towards",
    "via",
    "using",
    "at",
}


def parse_expense_input(raw_input: str) -> dict[str, object]:
    normalized = normalize_text(raw_input)
    amount = extract_amount(normalized)
    note = extract_note(normalized)
    categorization = categorize_text(note)

    return {
        "amount": amount,
        "category": categorization["category"],
        "note": note,
        "title": categorization["title"],
        "confidence": categorization["confidence"],
        "strategy": categorization["strategy"],
    }


def normalize_text(raw_input: str) -> str:
    return " ".join(raw_input.strip().split())


def extract_amount(text: str) -> float:
    match = AMOUNT_PATTERN.search(text)
    if match is None:
        raise ValueError("Could not detect amount")

    raw_amount = match.group(1).replace(",", "")
    amount = float(raw_amount)
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")
    return amount


def extract_note(text: str) -> str:
    note = AMOUNT_PATTERN.sub(" ", text, count=1)
    note = re.sub(r"[.,]", " ", note)
    tokens = [token for token in note.split() if token.lower() not in FILLER_WORDS]
    cleaned = " ".join(tokens).strip()
    return cleaned or "General expense"
