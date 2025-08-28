import os
from typing import Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

_mongo_client: Optional[MongoClient] = None
_database: Optional[Database] = None


def setup() -> None:
    """Initialize the MongoDB client and database, and ensure indexes exist."""
    global _mongo_client, _database

    mongodb_url = os.getenv("MONGODB_URL")  # Required on Render
    database_name = os.getenv("DATABASE_NAME", "subscription_manager")

    # Always connect with TLS (Atlas requires it)
    _mongo_client = MongoClient(mongodb_url, tls=True, tlsAllowInvalidCertificates=False)
    _database = _mongo_client[database_name]

    # Ensure indexes
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
