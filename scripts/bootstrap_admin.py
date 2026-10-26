#!/usr/bin/env python3
"""One-time admin bootstrap CLI for ParkWise AI.

Creates the first administrator account when no admins exist yet.
This is the only way to obtain an API key for initial setup in secure mode.

Usage:
    .venv/bin/python3 scripts/bootstrap_admin.py --username admin --display-name "Admin User"

Security:
    - Refuses to run if an active admin already exists
    - Generates a cryptographically secure random API key
    - Shows the key ONLY ONCE (not stored anywhere)
    - Never uses hard-coded default credentials
"""

import argparse
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend to path so we can import app modules
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.database import SessionLocal, init_db
from app.models import User
from app.security import hash_key


def bootstrap_admin(username: str, display_name: str, role: str = "admin") -> None:
    """Create first admin user if none exists."""
    # Initialize database tables if needed
    init_db()
    
    db = SessionLocal()
    try:
        # Check if any active admin already exists
        existing_admin = (
            db.query(User)
            .filter(User.role == "admin", User.is_active == True)
            .first()
        )
        
        if existing_admin:
            print(f"❌ ERROR: An active admin already exists (username: {existing_admin.username})")
            print("   If you've lost access, use the user management API to create a new admin.")
            print("   This bootstrap script only works for initial setup.")
            sys.exit(1)
        
        # Check if username is taken (even if inactive)
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            print(f"❌ ERROR: Username '{username}' is already taken")
            sys.exit(1)
        
        # Generate secure API key
        raw_key = "pk_" + secrets.token_urlsafe(32)
        api_key_hash = hash_key(raw_key)
        
        # Create user
        user = User(
            id=str(secrets.token_hex(16)),  # UUID-like ID
            username=username,
            display_name=display_name,
            role=role,
            is_active=True,
            api_key_hash=api_key_hash,
            created_at=datetime.now(timezone.utc),
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        print("=" * 80)
        print("✅ Admin user created successfully!")
        print("=" * 80)
        print()
        print(f"Username:    {username}")
        print(f"Display Name: {display_name}")
        print(f"Role:        {role}")
        print(f"User ID:     {user.id}")
        print()
        print("⚠️  IMPORTANT - COPY THIS API KEY NOW:")
        print("-" * 80)
        print(raw_key)
        print("-" * 80)
        print()
        print("This key is shown ONLY ONCE and cannot be recovered.")
        print("Store it securely (e.g., in a password manager).")
        print()
        print("Use this key in requests:")
        print(f"  curl -H 'X-API-Key: {raw_key}' http://localhost:8000/api/health")
        print()
        print("Or set it in your browser's localStorage:")
        print(f"  localStorage.setItem('parkwise-api-key', '{raw_key}')")
        print()
        print("=" * 80)
        
    except Exception as e:
        db.rollback()
        print(f"❌ ERROR: Failed to create admin user: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap the first admin user for ParkWise AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --username admin --display-name "System Administrator"
  %(prog)s --username operator1 --display-name "John Doe" --role operator

Note: This script only works if no active admin exists in the database.
        """
    )
    
    parser.add_argument(
        "--username",
        required=True,
        help="Unique username for the admin account"
    )
    parser.add_argument(
        "--display-name",
        required=True,
        help="Human-readable name (shown in UI)"
    )
    parser.add_argument(
        "--role",
        choices=["admin", "operator", "viewer"],
        default="admin",
        help="User role (default: admin)"
    )
    
    args = parser.parse_args()
    
    # Validate username format
    if not args.username.replace("_", "").replace("-", "").isalnum():
        print("❌ ERROR: Username must contain only alphanumeric characters, underscores, or hyphens")
        sys.exit(1)
    
    if len(args.username) < 3 or len(args.username) > 50:
        print("❌ ERROR: Username must be between 3 and 50 characters")
        sys.exit(1)
    
    print(f"🔐 Bootstrapping {args.role} user: {args.username}")
    print()
    
    bootstrap_admin(args.username, args.display_name, args.role)


if __name__ == "__main__":
    main()
