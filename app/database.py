import os
from typing import Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

_mongo_client: Optional[MongoClient] = None
_database: Optional[Database] = None


def setup() -> None:
    """Initialize the MongoDB client and database, and ensure indexes exist."""
    global _mongo_client, _database

    mongodb_url = os.getenv("MONGODB_URL")
    database_name = os.getenv("DATABASE_NAME")

    try:
        _mongo_client = MongoClient(mongodb_url)
        # Test the connection
        _mongo_client.admin.command('ping')
        _database = _mongo_client[database_name]

        # Ensure indexes for performance and constraints
        users: Collection = _database["users"]
        subscriptions: Collection = _database["subscriptions"]

        users.create_index("email", unique=True)
        subscriptions.create_index("owner_id")
        subscriptions.create_index("renewal_date")
        print("✅ MongoDB connected successfully!")
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        print("Please check your MongoDB connection string in the .env file")
        print("For local development, make sure MongoDB is running on localhost:27017")
        print("For MongoDB Atlas, check your connection string and credentials")
        print("Failed to initialize database: {e}")
        print("The application will start but database operations will fail.")
        print("Please ensure MongoDB is running and properly configured.")
        # Don't raise the exception, just set database to None
        _database = None


def get_db() -> Database:
    if _database is None:
        setup()
        if _database is None:
            raise Exception("Database is not available. Please check MongoDB connection.")
    return _database
