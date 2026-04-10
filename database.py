import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

# Check if keys are actually being loaded
if not url or not key:
    print("❌ ERROR: SUPABASE_URL or SUPABASE_KEY is missing from .env file!")
else:
    print(f"✅ Connecting to Supabase at: {url}")

supabase: Client = create_client(url, key)