from datetime import datetime
from typing import Optional, Annotated

from bson import ObjectId
from pydantic import BaseModel, EmailStr, Field
from pydantic.config import ConfigDict
from pydantic.functional_validators import BeforeValidator
from pydantic import field_serializer


def _to_object_id(value):
	if value is None:
		return None
	if isinstance(value, ObjectId):
		return value
	return ObjectId(str(value))


PyObjectId = Annotated[ObjectId, BeforeValidator(_to_object_id)]


class User(BaseModel):
	id: Optional[PyObjectId] = Field(default=None, alias="_id")
	email: EmailStr
	is_admin: bool = False
	created_at: Optional[datetime] = None
	notification_preferences: Optional[dict] = Field(default_factory=lambda: {
		"email_notifications": True,
		"browser_notifications": True,
		"reminder_days": [1, 3, 7]
	})

	model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

	@field_serializer("id")
	def serialize_id(self, value: Optional[ObjectId], _info):
		return str(value) if value is not None else None


class UserCreate(BaseModel):
	email: EmailStr
	password: str
	is_admin: bool = False
	notification_preferences: Optional[dict] = None


class UserInDB(User):
	hashed_password: str


class Subscription(BaseModel):
	id: Optional[PyObjectId] = Field(default=None, alias="_id")
	service_name: str
	cost: float
	billing_cycle: str
	renewal_date: datetime
	notes: Optional[str] = None
	is_shared: bool = False
	visibility: str = "private"  # private, shared, public
	owner_id: PyObjectId
	created_at: Optional[datetime] = None
	last_notified: Optional[datetime] = None

	model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

	@field_serializer("id", "owner_id")
	def serialize_object_ids(self, value: Optional[ObjectId], _info):
		return str(value) if value is not None else None


class SubscriptionCreate(BaseModel):
	service_name: str
	cost: float
	billing_cycle: str
	renewal_date: datetime
	notes: Optional[str] = None
	is_shared: bool = False
	visibility: str = "private"


class SubscriptionUpdate(BaseModel):
	service_name: Optional[str] = None
	cost: Optional[float] = None
	billing_cycle: Optional[str] = None
	renewal_date: Optional[datetime] = None
	notes: Optional[str] = None
	is_shared: Optional[bool] = None
	visibility: Optional[str] = None


class NotificationPreferences(BaseModel):
	email_notifications: bool = True
	browser_notifications: bool = True
	reminder_days: list[int] = [1, 3, 7]


class Token(BaseModel):
	access_token: str
	token_type: str


class Notification(BaseModel):
	id: Optional[PyObjectId] = Field(default=None, alias="_id")
	user_id: PyObjectId
	subscription_id: PyObjectId
	message: str
	type: str  # renewal_reminder, cost_alert, etc.
	is_read: bool = False
	created_at: Optional[datetime] = None

	model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

	@field_serializer("id", "user_id", "subscription_id")
	def serialize_object_ids(self, value: Optional[ObjectId], _info):
		return str(value) if value is not None else None
