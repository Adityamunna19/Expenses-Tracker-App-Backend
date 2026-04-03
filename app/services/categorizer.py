from __future__ import annotations

from app.database import get_connection


KEYWORD_RULES = {
    "Food": [
        "veg",
        "vegetable",
        "vegetables",
        "groceries",
        "grocery",
        "food",
        "swiggy",
        "zomato",
        "restaurant",
        "cafe",
        "tea",
        "coffee",
        "snack",
    ],
    "Travel": [
        "uber",
        "ola",
        "bus",
        "metro",
        "train",
        "auto",
        "taxi",
        "flight",
        "petrol",
        "fuel",
    ],
    "Housing": ["rent", "maintenance", "electricity", "water", "wifi", "broadband"],
    "Shopping": ["amazon", "flipkart", "shopping", "mall", "store", "clothes"],
    "Health": ["apollo", "medicine", "medical", "hospital", "clinic", "pharmacy"],
    "Bills": ["recharge", "mobile bill", "subscription", "bill"],
    "Transfers": ["phonepe", "gpay", "google pay", "paytm", "transfer", "upi"],
    "Credit": ["credit", "received back", "refund received", "cashback"],
    "Savings": [
        "saving",
        "savings",
        "saved",
        "deposit",
        "emergency fund",
        "rainy day",
        "fd",
        "fixed deposit",
        "recurring deposit",
        "rd",
    ],
}


def categorize_text(note: str) -> dict[str, object]:
    alias_match = find_alias_match(note)
    if alias_match:
        category, merchant_name, confidence = alias_match
        return {
            "category": category,
            "title": merchant_name,
            "confidence": confidence,
            "strategy": "merchant_alias",
        }

    haystack = note.lower()
    for category, keywords in KEYWORD_RULES.items():
        if any(keyword in haystack for keyword in keywords):
            return {
                "category": category,
                "title": build_title(note, category),
                "confidence": 0.86,
                "strategy": "keyword_rule",
            }

    return {
        "category": "Others",
        "title": build_title(note, "Others"),
        "confidence": 0.4,
        "strategy": "fallback",
    }


def find_alias_match(note: str) -> tuple[str, str, float] | None:
    haystack = note.lower()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT alias, merchant_clean, default_category, confidence
            FROM merchant_aliases
            ORDER BY confidence DESC, alias ASC
            """
        ).fetchall()

    for row in rows:
        if row["alias"] in haystack:
            return (
                row["default_category"],
                row["merchant_clean"],
                float(row["confidence"]),
            )
    return None


def build_title(note: str, fallback: str) -> str:
    cleaned = " ".join(word.capitalize() for word in note.split())
    return cleaned or fallback
