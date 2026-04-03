# PostgreSQL Migration Complete ✅

## **Executive Summary**

Your Expenses Tracker backend has been successfully migrated from SQLite to support **PostgreSQL**. The application now:

✅ Works with **both SQLite and PostgreSQL**  
✅ Auto-detects database based on `DATABASE_URL` environment variable  
✅ Is ready for deployment on **Render**  
✅ Maintains all functionality (users, transactions, reminders, etc.)  

---

## **What's New**

### 1. **Dual Database Support**
- **SQLite**: For local development (no setup needed)
- **PostgreSQL**: For production and cloud deployment

### 2. **Smart Database Detection**
```python
# The app checks if DATABASE_URL is set:
if DATABASE_URL exists → Use PostgreSQL
if DATABASE_URL missing → Use SQLite
```

### 3. **Helper Scripts**
- `register_user.py` - Register test users
- `db_manager.py` - Switch between databases
- `test_auth.py` - Verify authentication works

### 4. **Documentation**
- `POSTGRES_SETUP.md` - Detailed setup & deployment guide
- `QUICK_REFERENCE.md` - Quick commands reference
- `MIGRATION_SUMMARY.md` - What changed overview

---

## **Current Setup**

### Database: PostgreSQL (Local)
```
Host: localhost
Port: 5432
Database: expenses_tracker
User: postgres
```

### Test User
```
Email: admin@postgres.com
Password: adminpass123
```

---

## **Quick Start**

### 1. **Check Database Status**
```bash
python db_manager.py status
```

### 2. **Register a User**
```bash
python register_user.py
```

### 3. **View Data in PostgreSQL**
```bash
psql -d expenses_tracker
```

```sql
SELECT id, email, created_at FROM users;
SELECT id, amount, category, expense_at FROM transactions;
SELECT alias, merchant_clean, default_category FROM merchant_aliases;
```

### 4. **Start the Server**
```bash
python -m uvicorn app.main:app --reload
```

### 5. **Test Login**
Use Postman/REST Client to POST to:
```
POST http://localhost:8000/auth/login
Content-Type: application/json

{
  "email": "admin@postgres.com",
  "password": "adminpass123"
}
```

Response:
```json
{
  "access_token": "your_token_here",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "admin@postgres.com",
    "created_at": "2026-04-03T18:19:42.546921"
  }
}
```

---

## **Database Switching**

### Use Local PostgreSQL
```bash
python db_manager.py postgres postgresql://postgres@localhost:5432/expenses_tracker
# Restart server
```

### Use Local SQLite
```bash
python db_manager.py sqlite
# Restart server
```

### Use Remote PostgreSQL (Render)
```bash
python db_manager.py postgres postgresql://user:password@dpg-xxxxx.render.com:5432/database
# Restart server
```

---

## **File Changes Made**

### Modified Files
1. **app/database.py**
   - Added PostgreSQL connection support
   - Split init_db into init_sqlite_db() and init_postgres_db()
   - Updated get_connection() for dual database support
   - Added helper functions for both database types

2. **register_user.py**
   - Made database-agnostic
   - Works with both SQLite and PostgreSQL

3. **requirements.txt**
   - Added `psycopg2-binary==2.9.11`
   - Added `sqlalchemy==2.0.48`

4. **.env**
   - Added `DATABASE_URL` configuration

### New Files
1. **POSTGRES_SETUP.md** - Complete deployment guide
2. **MIGRATION_SUMMARY.md** - Overview of changes
3. **QUICK_REFERENCE.md** - Quick command reference
4. **db_manager.py** - Database switching utility
5. **test_auth.py** - Authentication testing

---

## **Deployment to Render**

### Step 1: Prepare Code
```bash
git add .
git commit -m "Add PostgreSQL support"
git push origin main
```

### Step 2: Create PostgreSQL on Render
- Go to https://render.com
- Create New → PostgreSQL
- Choose tier and region
- **Copy the Internal Database URL**

### Step 3: Deploy Web Service
- Create New → Web Service
- Connect GitHub repo
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Environment Variable:**
  - Key: `DATABASE_URL`
  - Value: Paste PostgreSQL URL from Step 2

### Step 4: Update Frontend
Change API URL from `http://localhost:8000` to your Render service URL

---

## **Database Schema**

Both SQLite and PostgreSQL have identical schemas:

```
┌─────────────────────────────────────────┐
│            USERS                         │
├─────────────────────────────────────────┤
│ id (PK)                                 │
│ email (UNIQUE)                          │
│ password_hash                           │
│ created_at                              │
└─────────────────────────────────────────┘
         ↓ (1 user has many)
┌─────────────────────────────────────────┐
│         AUTH_SESSIONS                    │
├─────────────────────────────────────────┤
│ id (PK)                                 │
│ user_id (FK)                            │
│ token_hash                              │
│ expires_at                              │
│ created_at                              │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│         TRANSACTIONS                     │
├─────────────────────────────────────────┤
│ id (PK)                                 │
│ user_id (FK)                            │
│ raw_message_id (FK)                     │
│ amount, currency, category              │
│ merchant_raw, merchant_clean            │
│ expense_at, notes, status               │
│ created_at, updated_at                  │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│      MERCHANT_ALIASES                    │
├─────────────────────────────────────────┤
│ id (PK)                                 │
│ alias                                   │
│ merchant_clean                          │
│ default_category                        │
│ confidence                              │
│ source                                  │
│ created_at                              │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│      RECEIVABLE_REMINDERS               │
├─────────────────────────────────────────┤
│ id (PK)                                 │
│ user_id (FK)                            │
│ expense_id (FK)                         │
│ title, amount, note                     │
│ remind_at, status                       │
│ received_transaction_id (FK)            │
│ created_at, updated_at                  │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│         RAW_MESSAGES                     │
├─────────────────────────────────────────┤
│ id (PK)                                 │
│ source_type, sender, message_text       │
│ received_at, parse_status               │
│ parse_error, created_at                 │
└─────────────────────────────────────────┘
```

---

## **Testing Commands**

### Test Database Connection
```bash
python test_auth.py
```

### Test User Registration
```bash
python register_user.py
```

### Test Server Startup
```bash
python -m uvicorn app.main:app --reload
# Visit http://localhost:8000/docs for API docs
```

### Test API with cURL
```bash
# Login
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@postgres.com",
    "password": "adminpass123"
  }'

# Get current user (replace TOKEN with actual token)
curl -X GET "http://localhost:8000/auth/me" \
  -H "Authorization: Bearer TOKEN"
```

---

## **Troubleshooting**

### PostgreSQL Won't Start
```bash
# Check if running
brew services list

# Start it
brew services start postgresql@15

# View logs
tail -f /opt/homebrew/var/postgresql@15/postmaster.log
```

### Database Connection Failed
```bash
# Verify database exists
psql -l | grep expenses_tracker

# Create if missing
/opt/homebrew/opt/postgresql@15/bin/createdb expenses_tracker
```

### User Registration Failed
```bash
# Check users table
psql -d expenses_tracker -c "SELECT * FROM users;"

# Check if tables exist
psql -d expenses_tracker -c "\dt"
```

### Wrong Database in Use
```bash
# Check which one is active
python db_manager.py status

# Switch to correct one
python db_manager.py postgres postgresql://...
python db_manager.py sqlite
```

---

## **Migration Tips**

### Backup SQLite Data
```bash
sqlite3 data/expenses.db ".dump" > backup.sql
```

### Export PostgreSQL Data
```bash
pg_dump -d expenses_tracker > backup.sql
```

### Copy Data Between Databases
This requires manual migration as schemas differ. For now:
1. Keep SQLite for local dev
2. Start fresh with PostgreSQL in production
3. Users register anew on the cloud version

---

## **Environment Variables**

### .env File Format
```dotenv
# Frontend CORS
FRONTEND_ORIGINS=http://localhost:5173/,http://localhost:3000/

# Database (leave empty for SQLite)
DATABASE_URL=postgresql://postgres@localhost:5432/expenses_tracker

# OR for Render:
# DATABASE_URL=postgresql://user:pass@dpg-xxxxx.render.com:5432/db
```

---

## **Next Steps**

1. ✅ **Local Testing** - Run the app locally with PostgreSQL
2. ✅ **Register Users** - Test user creation and login
3. ⬜ **Frontend Testing** - Test with your frontend app
4. ⬜ **Deploy to Render** - Follow POSTGRES_SETUP.md
5. ⬜ **Production Testing** - Test all features in production

---

## **Support & Resources**

- **PostgreSQL Docs:** https://www.postgresql.org/docs/
- **Render Docs:** https://render.com/docs
- **psycopg2 Docs:** https://www.psycopg.org/
- **FastAPI Docs:** https://fastapi.tiangolo.com/

---

## **Questions?**

Refer to these files in order:
1. `QUICK_REFERENCE.md` - For quick commands
2. `POSTGRES_SETUP.md` - For detailed setup
3. `MIGRATION_SUMMARY.md` - For overview of changes

**Happy coding!** 🚀
