import os
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
import firebase_admin
from firebase_admin import credentials, messaging

def initialize_firebase():
    """Starts the Firebase connection using your downloaded JSON key."""
    try:
        # Make sure 'firebase-adminsdk.json' is in the same folder!
        if not firebase_admin._apps:
            cred = credentials.Certificate("firebase-adminsdk.json")
            firebase_admin.initialize_app(cred)
            print("✈️ Firebase initialized successfully.")
    except Exception as e:
        print(f"⚠️ Warning: Firebase not initialized. {e}")

def check_and_send_reminders(supabase_client):
    """The brain of the operation: checks DB and sends notifications."""
    print(f"[{datetime.now()}] 📡 Scanning radar for 12-Hour Reminders...")
    try:
        # 1. Find users who opted in and have a push token
        users_res = supabase_client.table("user_settings") \
            .select("*") \
            .eq("reminders_enabled", True) \
            .not_is_null("push_token") \
            .execute()
        
        now = datetime.now(timezone.utc)

        for user in users_res.data:
            user_id = user['user_id']
            token = user['push_token']
            
            # 2. Find their most recent transaction
            tx_res = supabase_client.table("transactions") \
                .select("created_at") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()
            
            needs_reminder = False
            
            if not tx_res.data:
                needs_reminder = True  # They have never logged a transaction
            else:
                last_tx_time = datetime.fromisoformat(tx_res.data[0]['created_at'].replace('Z', '+00:00'))
                if now - last_tx_time > timedelta(hours=12):
                    needs_reminder = True

            # 3. Prevent spamming (Check if we already pinged them in the last 12 hours)
            last_notified = user.get('last_notified_at')
            if last_notified:
                last_notified_time = datetime.fromisoformat(last_notified.replace('Z', '+00:00'))
                if now - last_notified_time < timedelta(hours=12):
                    needs_reminder = False 
            
            # 4. Fire the Push Notification
            if needs_reminder:
                try:
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title="Cockpit Check-in ✈️",
                            body="It's been 12 hours. Time to log your recent transactions and clear your radar!",
                        ),
                        token=token,
                    )
                    messaging.send(message)
                    
                    # Log the successful ping in Supabase
                    supabase_client.table("user_settings") \
                        .update({"last_notified_at": now.isoformat()}) \
                        .eq("user_id", user_id) \
                        .execute()
                    
                    print(f"✅ Reminder sent to User: {user_id}")
                except Exception as msg_error:
                    print(f"❌ Failed to send to {user_id}: {msg_error}")
                
    except Exception as e:
        print(f"🚨 Scheduler Error: {e}")

def start_scheduler(supabase_client):
    """Wakes up the background worker when FastAPI starts."""
    initialize_firebase()
    
    scheduler = BackgroundScheduler()
    # Runs the check_and_send_reminders function every 60 minutes
    scheduler.add_job(check_and_send_reminders, 'interval', minutes=60, args=[supabase_client]) 
    scheduler.start()
    print("⏱️ Background Scheduler Started")