from getpass import getpass
from argon2 import PasswordHasher
from sqlalchemy import select
from backend.config import settings
from backend.db import init_db, SessionLocal
from backend.models import Admin

def main():
    settings.validate_secrets(); init_db()
    username=input("User username: ").strip()
    if not username: raise SystemExit("Username is required")
    role_input = input("Role (ADMIN, GATE, CANTEEN) [ADMIN]: ").strip().upper() or "ADMIN"
    if role_input not in ("ADMIN", "GATE", "CANTEEN"):
        raise SystemExit("Invalid role. Must be ADMIN, GATE, or CANTEEN.")
    password=getpass("New password (minimum 14 characters): ")
    if len(password)<14: raise SystemExit("Password must be at least 14 characters")
    db=SessionLocal()
    try:
        if db.scalar(select(Admin).where(Admin.username==username)): raise SystemExit("That username already exists")
        db.add(Admin(username=username, password_hash=PasswordHasher().hash(password), role=role_input))
        db.commit()
    finally: db.close()
    print(f"User '{username}' with role '{role_input}' created successfully.")

if __name__=="__main__": main()
