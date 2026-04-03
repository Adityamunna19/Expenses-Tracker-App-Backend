# Migration Complete: PostgreSQL Setup ✅

## **What Was Done**

Your Expenses Tracker backend has been successfully migrated to support **PostgreSQL** in addition to SQLite. The app now automatically detects which database to use based on environment variables.

---

## **Current Status**

### ✅ Completed
- Installed PostgreSQL 15 on your Mac
- Created `expenses_tracker` database
- Updated database layer to support both SQLite and PostgreSQL
- Updated `register_user.py` to work with both database types
- Tested user registration with PostgreSQL
- Created comprehensive setup guide

### 📦 New Dependencies Added
```
psycopg2-binary==2.9.11
sqlalchemy==2.0.48
```

---

## **How to Use**

### **Option 1: Use PostgreSQL Locally (Current Setup)**
Everything is already configured! Your `.env` file points to local PostgreSQL:

```env
DATABASE_URL=postgresql://postgres@localhost:5432/expenses_tracker
```

**To register a user:**
```bash
python register_user.py
# Enter email and password when prompted
```

**To view data:**
```bash
psql -d expenses_tracker
```

Then run SQL commands like:
```sql
SELECT * FROM users;
SELECT * FROM transactions;
SELECT * FROM merchant_aliases;
```

---

### **Option 2: Switch Back to SQLite (Local)**
If you want to use SQLite instead:

1. Edit `.env` and comment out DATABASE_URL:
```env
# DATABASE_URL=postgresql://postgres@localhost:5432/expenses_tracker
```

2. The app will automatically use SQLite at `data/expenses.db`

---

### **Option 3: Deploy to Render (Production)**

Follow the detailed steps in `POSTGRES_SETUP.md`:

1. Create PostgreSQL database on Render
2. Create Web Service on Render
3. Set `DATABASE_URL` environment variable in Render
4. Push code to GitHub and deploy

---

## **Test User Credentials (PostgreSQL)**

Use these to test your app:
```
Email: admin@postgres.com
Password: adminpass123
```

---

## **Database Architecture**

Both SQLite and PostgreSQL support the same schema:
- `users` - User accounts
- `auth_sessions` - Login sessions
- `raw_messages` - Raw message data
- `transactions` - Expenses/transactions
- `merchant_aliases` - Merchant name mappings
- `receivable_reminders` - Payment reminders

---

## **Files Modified**

1. **app/database.py** - Added PostgreSQL support
2. **register_user.py** - Made database-agnostic
3. **requirements.txt** - Added psycopg2 and sqlalchemy
4. **.env** - Added DATABASE_URL configuration

---

## **Next Steps**

1. **Test your API:**
   ```bash
   python -m uvicorn app.main:app --reload
   ```

2. **Try login with:** `admin@postgres.com` / `adminpass123`

3. **When ready to deploy:** Follow `POSTGRES_SETUP.md` for Render deployment

4. **View data:** Use `psql` command or a GUI like [pgAdmin](https://www.pgadmin.org/)

---

## **Common Commands**

```bash
# View PostgreSQL databases
psql -l

# Connect to expenses_tracker
psql -d expenses_tracker

# View all tables
\dt

# View schema of a table
\d users

# Register new user
python register_user.py

# Restart PostgreSQL
brew services restart postgresql@15

# Stop PostgreSQL
brew services stop postgresql@15
```

---

## **Need Help?**

- Check `POSTGRES_SETUP.md` for detailed deployment instructions
- PostgreSQL Docs: https://www.postgresql.org/docs/
- Render Docs: https://render.com/docs

You're all set! 🚀
