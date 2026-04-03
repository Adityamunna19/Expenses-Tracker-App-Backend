#!/usr/bin/env python3
"""
Database management utility for switching between SQLite and PostgreSQL
"""

import sys
import subprocess
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def switch_to_sqlite():
    """Switch to SQLite database"""
    env_file = Path(".env")
    content = env_file.read_text()
    
    # Comment out DATABASE_URL
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        if line.strip().startswith('DATABASE_URL='):
            new_lines.append(f"# {line}")
        else:
            new_lines.append(line)
    
    env_file.write_text('\n'.join(new_lines))
    print("✅ Switched to SQLite")
    print("   Database: data/expenses.db")
    print("   Restart your server for changes to take effect")

def switch_to_postgres(url: str):
    """Switch to PostgreSQL database"""
    env_file = Path(".env")
    content = env_file.read_text()
    
    # Update or add DATABASE_URL
    lines = content.split('\n')
    new_lines = []
    found = False
    
    for line in lines:
        if line.strip().startswith('DATABASE_URL='):
            new_lines.append(f"DATABASE_URL={url}")
            found = True
        elif line.strip().startswith('# DATABASE_URL='):
            new_lines.append(f"DATABASE_URL={url}")
            found = True
        else:
            new_lines.append(line)
    
    if not found:
        new_lines.append(f"DATABASE_URL={url}")
    
    env_file.write_text('\n'.join(new_lines))
    print("✅ Switched to PostgreSQL")
    print(f"   Connection: {url.split('@')[1] if '@' in url else '...'}")
    print("   Restart your server for changes to take effect")

def show_status():
    """Show current database configuration"""
    from dotenv import load_dotenv
    import os
    
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    
    print("\n=== Database Configuration ===\n")
    if db_url:
        parts = db_url.split('@')
        host_port = parts[1].split(':') if len(parts) > 1 else ['unknown', 'unknown']
        host = host_port[0]
        port = host_port[1].split('/')[0] if len(host_port) > 1 else 'unknown'
        db_name = parts[1].split('/')[-1] if '/' in parts[1] else 'unknown'
        
        print(f"Active: PostgreSQL")
        print(f"  Host: {host}")
        print(f"  Port: {port}")
        print(f"  Database: {db_name}")
    else:
        print(f"Active: SQLite")
        print(f"  File: data/expenses.db")
    print()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_status()
        print("Usage:")
        print("  python db_manager.py status          - Show current database")
        print("  python db_manager.py sqlite          - Switch to SQLite")
        print("  python db_manager.py postgres <url>  - Switch to PostgreSQL")
        print("\nExample:")
        print("  python db_manager.py postgres postgresql://postgres@localhost:5432/expenses_tracker")
        sys.exit(0)
    
    command = sys.argv[1].lower()
    
    if command == "status":
        show_status()
    elif command == "sqlite":
        switch_to_sqlite()
    elif command == "postgres":
        if len(sys.argv) < 3:
            print("❌ Error: PostgreSQL URL required")
            print("Usage: python db_manager.py postgres <url>")
            print("Example: python db_manager.py postgres postgresql://postgres@localhost:5432/expenses_tracker")
            sys.exit(1)
        switch_to_postgres(sys.argv[2])
    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)
