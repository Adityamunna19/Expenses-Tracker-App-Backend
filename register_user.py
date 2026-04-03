#!/usr/bin/env python3
"""
Simple script to register a test user in the Expenses Tracker app.
Make sure the backend server is running before executing this script.
"""

import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from app.services.auth import hash_password
from app.database import get_connection, USE_POSTGRESQL


def register_user(email: str, password: str) -> dict:
    """Register a new user directly in the database."""
    
    # Validate password
    if len(password) < 8:
        print("❌ Error: Password must be at least 8 characters long")
        return {}
    
    normalized_email = email.lower()
    password_hash = hash_password(password)
    
    try:
        with get_connection() as connection:
            if USE_POSTGRESQL:
                cursor = connection.cursor()
                # Check if email already exists
                cursor.execute(
                    "SELECT id FROM users WHERE email = %s",
                    (normalized_email,),
                )
                existing = cursor.fetchone()
                
                if existing is not None:
                    print(f"❌ Error: Email '{email}' is already registered")
                    return {}
                
                # Insert new user
                cursor.execute(
                    """
                    INSERT INTO users (email, password_hash)
                    VALUES (%s, %s)
                    RETURNING id, email, created_at
                    """,
                    (normalized_email, password_hash),
                )
                
                user = cursor.fetchone()
                result = {
                    "id": user[0],
                    "email": user[1],
                    "created_at": str(user[2]),
                }
            else:
                # SQLite
                # Check if email already exists
                existing = connection.execute(
                    "SELECT id FROM users WHERE email = ?",
                    (normalized_email,),
                ).fetchone()
                
                if existing is not None:
                    print(f"❌ Error: Email '{email}' is already registered")
                    return {}
                
                # Insert new user
                cursor = connection.execute(
                    """
                    INSERT INTO users (email, password_hash)
                    VALUES (?, ?)
                    """,
                    (normalized_email, password_hash),
                )
                
                user_id = cursor.lastrowid
                
                # Fetch the created user
                user = connection.execute(
                    "SELECT id, email, created_at FROM users WHERE id = ?",
                    (user_id,),
                ).fetchone()
                
                result = {
                    "id": user["id"],
                    "email": user["email"],
                    "created_at": user["created_at"],
                }
            
            print(f"✅ User registered successfully!")
            print(f"   Email: {result['email']}")
            print(f"   ID: {result['id']}")
            print(f"   Created at: {result['created_at']}")
            
            return result
            
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}


if __name__ == "__main__":
    # Example: Register a test user
    print("=== Expenses Tracker - User Registration ===\n")
    
    # You can modify these or accept command line arguments
    email = input("Enter email: ").strip()
    password = input("Enter password (min 8 chars): ").strip()
    
    if not email or not password:
        print("❌ Error: Email and password cannot be empty")
        sys.exit(1)
    
    register_user(email, password)
    
    print("\n💡 You can now login with these credentials!")
