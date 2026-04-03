# PostgreSQL & Render Deployment Guide

## Overview
Your Expenses Tracker app now supports both SQLite (local development) and PostgreSQL (production/Render).

---

## **Option 1: Local PostgreSQL Setup (macOS)**

### 1.1 Install PostgreSQL using Homebrew
```bash
brew install postgresql@15
brew services start postgresql@15
```

### 1.2 Create a local PostgreSQL database
```bash
createdb expenses_tracker
```

### 1.3 Update your `.env` file
```env
FRONTEND_ORIGINS=http://localhost:5173/
DATABASE_URL=postgresql://postgres:@localhost:5432/expenses_tracker
```

### 1.4 Restart your backend
The database will be initialized automatically on startup.

---

## **Option 2: Deploy to Render (Production)**

### Step 1: Create a Render Account
- Go to https://render.com
- Sign up with your GitHub account

### Step 2: Create a PostgreSQL Database on Render
1. Go to Dashboard → Create New → PostgreSQL
2. Configure:
   - **Name:** expenses-tracker-db
   - **Database:** expenses_tracker
   - **User:** postgres
   - **Region:** Choose closest to you
   - **PostgreSQL Version:** 15
   - **Plan:** Free tier (or paid if needed)

3. Click "Create Database"
4. **Copy the Internal Database URL** (you'll see it in the "Connections" section)

### Step 3: Deploy Backend to Render
1. Push your code to GitHub:
```bash
git add .
git commit -m "Add PostgreSQL support"
git push origin main
```

2. On Render Dashboard → Create New → Web Service
3. Connect your GitHub repository
4. Configure:
   - **Name:** expenses-tracker-api
   - **Environment:** Python 3
   - **Build Command:** 
     ```
     pip install -r requirements.txt
     ```
   - **Start Command:** 
     ```
     python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
     ```
   - **Plan:** Free or Starter

5. Add Environment Variables:
   - **Key:** `DATABASE_URL`
   - **Value:** Paste the PostgreSQL URL from Step 2

6. Click "Deploy Web Service"

### Step 4: Update Frontend
Update your frontend's API URL from `http://localhost:8000` to the Render service URL (e.g., `https://expenses-tracker-api.render.com`)

---

## **Example DATABASE_URL Format**
```
postgresql://username:password@host:port/database_name
```

For Render, it looks like:
```
postgresql://expenses_tracker_user:your_password@dpg-xxxxx.render.com:5432/expenses_tracker
```

---

## **Switching Between SQLite and PostgreSQL**

### Use SQLite (Local Development)
```bash
# Leave DATABASE_URL commented or empty in .env
# The app will use SQLite automatically
```

### Use PostgreSQL
```bash
# Add DATABASE_URL to .env with your PostgreSQL connection string
DATABASE_URL=postgresql://user:password@host:port/database
```

---

## **How the App Knows Which Database to Use**
The app checks if `DATABASE_URL` is set in `.env`:
- ✅ If `DATABASE_URL` exists → Use PostgreSQL
- ❌ If `DATABASE_URL` is empty/missing → Use SQLite

---

## **Common Issues**

### Issue: "DATABASE_URL not set" 
**Solution:** Make sure `DATABASE_URL` is in your `.env` file with the correct connection string.

### Issue: PostgreSQL connection fails
**Solution:** Check:
1. PostgreSQL service is running (`brew services list`)
2. Database exists (`psql -l`)
3. Connection string format is correct
4. User has proper permissions

### Issue: Render deployment fails
**Solution:**
1. Check the deployment logs in Render dashboard
2. Verify DATABASE_URL is set in Render environment variables
3. Ensure PostgreSQL database is running

---

## **Migrating Data from SQLite to PostgreSQL**

If you have existing data in SQLite and want to move it:

```bash
# Export SQLite data
sqlite3 data/expenses.db ".dump" > backup.sql

# Import to PostgreSQL (requires manual script)
# PostgreSQL has different syntax than SQLite
```

For now, the best approach:
1. Keep using SQLite locally
2. Start fresh with PostgreSQL in production
3. Users will register/login again on the new system

---

## **Next Steps**
1. ✅ Choose between local PostgreSQL or Render
2. ✅ Update `.env` with DATABASE_URL
3. ✅ Restart your backend
4. ✅ Test login/register
5. ✅ Deploy to Render when ready

For questions, check [Render Docs](https://render.com/docs) or [PostgreSQL Docs](https://www.postgresql.org/docs/).
