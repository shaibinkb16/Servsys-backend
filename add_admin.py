#!/usr/bin/env python3
import os
from pymongo import MongoClient
from passlib.context import CryptContext
from datetime import datetime
import getpass
from dotenv import load_dotenv

load_dotenv()

def add_admin_direct():
    """Directly add admin user to MongoDB"""
    
    # Get MongoDB connection details from environment
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    database_name = os.getenv("DATABASE_NAME", "subscription_manager")
    
    # Connect to MongoDB
    client = MongoClient(mongodb_url)
    db = client[database_name]
    
    # Get user input
    print("=== Add Admin User Directly to MongoDB ===")
    email = input("Email: ").strip()
    
    # Check if user already exists
    existing_user = db.users.find_one({"email": email})
    if existing_user:
        print(f"User with email {email} already exists!")
        client.close()
        return False
    
    # Get password
    while True:
        password = getpass.getpass("Password: ")
        confirm_password = getpass.getpass("Confirm Password: ")
        
        if password != confirm_password:
            print("Passwords don't match. Try again.")
        elif len(password) < 6:
            print("Password must be at least 6 characters long.")
        else:
            break
    
    # Hash password
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed_password = pwd_context.hash(password)
    
    # Create user document
    user_data = {
        "email": email,
        "hashed_password": hashed_password,
        "is_admin": True,
        "created_at": datetime.utcnow()
    }
    
    # Insert user
    result = db.users.insert_one(user_data)
    
    if result.inserted_id:
        print(f"Admin user {email} created successfully!")
        client.close()
        return True
    else:
        print("Failed to create admin user.")
        client.close()
        return False

if __name__ == "__main__":
    add_admin_direct()