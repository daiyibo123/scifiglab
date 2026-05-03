"""
Create an admin user from the command line.

Usage:
    python -m scripts.create_admin
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database.session import SessionLocal
from app.database.init_db import init_db
from app.services.auth_service import create_user


def main():
    init_db()
    db = SessionLocal()
    try:
        username = input("Admin username: ").strip()
        email = input("Admin email: ").strip()
        password = input("Admin password: ").strip()
        if not username or not email or not password:
            print("All fields are required.")
            return
        user = create_user(db, username=username, email=email, password=password)
        print(f"User created: {user.username} (id={user.id})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
