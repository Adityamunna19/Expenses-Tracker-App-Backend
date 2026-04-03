# Expenses Tracker Backend

FastAPI backend for a smart-input expense tracker. The MVP is built around one fast entry field such as `100 vegetables` or `250 swiggy`.

## What This Backend Supports

- Parse natural expense input with `POST /parse-expense`
- Save confirmed expenses with `POST /expenses`
- List saved expenses with `GET /expenses`
- Update or soft-delete expenses
- Get totals and category breakdowns
- Export expense data as CSV

## Stack

- FastAPI
- SQLite
- Pydantic

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

The API runs on `http://127.0.0.1:8000`.

## Core Flow

1. User types a single-line expense like `100 vegetables`.
2. Frontend sends it to `POST /parse-expense`.
3. Backend extracts amount, category, and note.
4. Frontend shows a preview.
5. User confirms and frontend saves it with `POST /expenses`.

## API Endpoints

- `GET /health`
- `POST /parse-expense`
- `GET /expenses`
- `POST /expenses`
- `PUT /expenses/{expense_id}`
- `DELETE /expenses/{expense_id}`
- `GET /expenses/summary`
- `GET /dashboard`
- `GET /expenses/export`

## Example Parse Request

```bash
curl -X POST http://127.0.0.1:8000/parse-expense \
  -H "Content-Type: application/json" \
  -d '{
    "input": "100 vegetables"
  }'
```

Example response:

```json
{
  "amount": 100,
  "category": "Food",
  "note": "vegetables",
  "title": "Vegetables",
  "confidence": 0.86,
  "strategy": "keyword_rule"
}
```

## Example Save Request

```bash
curl -X POST http://127.0.0.1:8000/expenses \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 100,
    "category": "Food",
    "note": "vegetables",
    "title": "Vegetables"
  }'
```

## Notes

- Data is stored in `data/expenses.db`
- CORS origins can be configured with `FRONTEND_ORIGINS`
- Merchant aliases and keyword rules can be extended in the service layer later for smarter categorization
