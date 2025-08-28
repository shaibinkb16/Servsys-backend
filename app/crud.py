from datetime import datetime, timedelta
from typing import List, Optional

from bson import ObjectId
from passlib.context import CryptContext

from .database import get_db
from .models import Subscription, SubscriptionCreate, SubscriptionUpdate, User, UserCreate, UserInDB, NotificationPreferences

# Local password hasher to avoid circular import with auth
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
	return pwd_context.hash(password)


def get_user_by_email(email: str) -> Optional[UserInDB]:
	db = get_db()
	data = db.users.find_one({"email": email})
	if data:
		return UserInDB(**data)
	return None


def list_users() -> List[User]:
	db = get_db()
	return [User(**doc) for doc in db.users.find()]


def create_user(user: UserCreate) -> User:
	db = get_db()
	hashed_password = get_password_hash(user.password)
	doc = {
		"email": user.email,
		"hashed_password": hashed_password,
		"is_admin": user.is_admin,
		"created_at": datetime.utcnow(),
		"notification_preferences": user.notification_preferences or {
			"email_notifications": True,
			"browser_notifications": True,
			"reminder_days": [1, 3, 7]
		}
	}
	result = db.users.insert_one(doc)
	created = db.users.find_one({"_id": result.inserted_id})
	return User(**created)


def update_user_notification_preferences(user_id: str, preferences: NotificationPreferences) -> bool:
	db = get_db()
	result = db.users.update_one(
		{"_id": ObjectId(user_id)},
		{"$set": {"notification_preferences": preferences.model_dump()}}
	)
	return result.modified_count > 0


def get_all_subscriptions(skip: int = 0, limit: int = 100) -> List[Subscription]:
	db = get_db()
	cursor = db.subscriptions.find().skip(skip).limit(limit)
	return [Subscription(**doc) for doc in cursor]


def get_user_subscriptions(user_id: str, skip: int = 0, limit: int = 100) -> List[Subscription]:
	db = get_db()
	cursor = db.subscriptions.find({"owner_id": ObjectId(user_id)}).skip(skip).limit(limit)
	return [Subscription(**doc) for doc in cursor]


def get_accessible_subscriptions(user_id: str, skip: int = 0, limit: int = 100) -> List[Subscription]:
	db = get_db()
	cursor = db.subscriptions.find({
		"$or": [
			{"owner_id": ObjectId(user_id)},
			{"visibility": "shared"},
			{"is_shared": True}
		]
	}).skip(skip).limit(limit)
	return [Subscription(**doc) for doc in cursor]


def get_upcoming_subscriptions_all(within_days: int = 7, skip: int = 0, limit: int = 100) -> List[Subscription]:
	db = get_db()
	now = datetime.utcnow()
	until = now + timedelta(days=within_days)
	cursor = db.subscriptions.find({
		"renewal_date": {"$gte": now, "$lte": until}
	}).sort("renewal_date", 1).skip(skip).limit(limit)
	return [Subscription(**doc) for doc in cursor]


def get_upcoming_subscriptions_accessible(user_id: str, within_days: int = 7, skip: int = 0, limit: int = 100) -> List[Subscription]:
	db = get_db()
	now = datetime.utcnow()
	until = now + timedelta(days=within_days)
	cursor = db.subscriptions.find({
		"$and": [
			{"renewal_date": {"$gte": now, "$lte": until}},
			{"$or": [
				{"owner_id": ObjectId(user_id)},
				{"visibility": "shared"},
				{"is_shared": True}
			]},
		],
	}).sort("renewal_date", 1).skip(skip).limit(limit)
	return [Subscription(**doc) for doc in cursor]


def get_subscription(subscription_id: str) -> Optional[Subscription]:
	db = get_db()
	doc = db.subscriptions.find_one({"_id": ObjectId(subscription_id)})
	return Subscription(**doc) if doc else None


def create_subscription(subscription: SubscriptionCreate, owner_id: str) -> Subscription:
	db = get_db()
	doc = {
		**subscription.model_dump(),
		"owner_id": ObjectId(owner_id),
		"created_at": datetime.utcnow(),
	}
	result = db.subscriptions.insert_one(doc)
	created = db.subscriptions.find_one({"_id": result.inserted_id})
	return Subscription(**created)


def update_subscription(subscription_id: str, subscription: SubscriptionUpdate) -> Subscription:
	db = get_db()
	update_data = {k: v for k, v in subscription.model_dump().items() if v is not None}
	db.subscriptions.update_one({"_id": ObjectId(subscription_id)}, {"$set": update_data})
	updated = db.subscriptions.find_one({"_id": ObjectId(subscription_id)})
	return Subscription(**updated)


def delete_subscription(subscription_id: str) -> None:
	db = get_db()
	db.subscriptions.delete_one({"_id": ObjectId(subscription_id)})


def get_user_notifications(user_id: str, limit: int = 50) -> List[dict]:
	db = get_db()
	cursor = db.notifications.find({"user_id": user_id}).sort("created_at", -1).limit(limit)
	return list(cursor)


def mark_notification_read(notification_id: str) -> bool:
	db = get_db()
	result = db.notifications.update_one(
		{"_id": ObjectId(notification_id)},
		{"$set": {"is_read": True}}
	)
	return result.modified_count > 0


def get_unread_notification_count(user_id: str) -> int:
	db = get_db()
	return db.notifications.count_documents({
		"user_id": user_id,
		"is_read": False
	})
