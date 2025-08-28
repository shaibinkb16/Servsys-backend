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

    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    database_name = os.getenv("DATABASE_NAME", "subscription_manager")

    _mongo_client = MongoClient(mongodb_url)
    _database = _mongo_client[database_name]

    # Ensure indexes for performance and constraints
    users: Collection = _database["users"]
    subscriptions: Collection = _database["subscriptions"]

    users.create_index("email", unique=True)
    subscriptions.create_index("owner_id")
    subscriptions.create_index("renewal_date")


def get_db() -> Database:
    if _database is None:
        setup()
        assert _database is not None
    return _database
