# Quick Reference: SQLite ↔ PostgreSQL

## **Current Setup**
✅ **Active Database:** PostgreSQL at `localhost:5432/expenses_tracker`

---

## **Switching Databases**

### Switch to SQLite (Local)
```bash
python db_manager.py sqlite
```

### Switch to PostgreSQL (Local)
```bash
python db_manager.py postgres postgresql://postgres@localhost:5432/expenses_tracker
```

### Switch to PostgreSQL (Render)
```bash
python db_manager.py postgres postgresql://user:password@dpg-xxxxx.render.com:5432/database_name
```

### Check Current Database
```bash
python db_manager.py status
```

---

## **Accessing Data**

### PostgreSQL (Local)
```bash
# Connect to database
psql -d expenses_tracker

# View users
SELECT * FROM users;

# View transactions
SELECT * FROM transactions;

# Exit
\q
```

### SQLite (Local)
```bash
# Connect to database
sqlite3 data/expenses.db

# View users
SELECT * FROM users;

# View transactions
SELECT * FROM transactions;

# Exit
.quit
```

---

## **User Registration**

Register a new test user:
```bash
python register_user.py
# Enter email when prompted
# Enter password (min 8 characters)
```

---

## **Current Test User**
```
Email: admin@postgres.com
Password: adminpass123
```

---

## **Restart Server**

After switching databases, restart your backend:
```bash
# Stop current server (Ctrl+C)
# Then restart:
python -m uvicorn app.main:app --reload
```

---

## **PostgreSQL Service Management**

```bash
# Start PostgreSQL
brew services start postgresql@15

# Stop PostgreSQL
brew services stop postgresql@15

# Restart PostgreSQL
brew services restart postgresql@15

# Check status
brew services list
```

---

## **Deployment Checklist**

- [ ] Code pushed to GitHub
- [ ] PostgreSQL database created on Render
- [ ] Web Service created on Render
- [ ] `DATABASE_URL` set in Render environment
- [ ] Frontend updated with API URL
- [ ] Test login works in production

For detailed instructions, see `POSTGRES_SETUP.md`

---

## **Troubleshooting**

| Issue | Solution |
|-------|----------|
| "role 'postgres' does not exist" | Run: `/opt/homebrew/opt/postgresql@15/bin/createuser -s postgres` |
| "database does not exist" | Run: `/opt/homebrew/opt/postgresql@15/bin/createdb expenses_tracker` |
| Connection timeout | Check if PostgreSQL is running: `brew services list` |
| SQLite file not found | Use SQLite mode: `python db_manager.py sqlite` |
| "no such table" | Tables auto-initialize on app startup |

---

## **File Locations**

- **SQLite:** `data/expenses.db`
- **Configuration:** `.env`
- **Backup SQLite:** `sqlite3 data/expenses.db ".dump" > backup.sql`
- **PostgreSQL Logs:** `/opt/homebrew/var/postgresql@15/postmaster.log`

---

## **Useful Links**

- PostgreSQL Docs: https://www.postgresql.org/docs/
- Render Docs: https://render.com/docs
- psycopg2 Docs: https://www.psycopg.org/
