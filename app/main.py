import os
from datetime import timedelta, datetime
from typing import List

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

from . import ai_insights, auth, crud, database, notifications
from .models import Subscription, SubscriptionCreate, SubscriptionUpdate, Token, User, UserCreate, UserInDB, NotificationPreferences

load_dotenv()

app = FastAPI(title="Subscription Manager API")

allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000").split(",")
app.add_middleware(
	CORSMiddleware,
	allow_origins=allowed_origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# Initialize database with error handling
try:
    database.setup()
except Exception as e:
    print(f"Failed to initialize database: {e}")
    print("The application will start but database operations will fail.")
    print("Please ensure MongoDB is running and properly configured.")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Pydantic models for password reset
class ForgotPasswordRequest(BaseModel):
	email: EmailStr

class VerifyOTPRequest(BaseModel):
	email: EmailStr
	otp: str

class ResetPasswordRequest(BaseModel):
	email: EmailStr
	otp: str
	new_password: str


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
	return auth.get_current_user(token)


async def get_current_admin(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
	if not current_user.is_admin:
		raise HTTPException(status_code=403, detail="Not enough permissions")
	return current_user


def _seed_demo_users() -> None:
	if os.getenv("SEED_DEMO_USERS", "true").lower() != "true":
		return
	try:
		seed = [
			UserCreate(email="admin@demo.com", password="Admin@123", is_admin=True),
			UserCreate(email="alice@demo.com", password="Alice@123", is_admin=False),
			UserCreate(email="bob@demo.com", password="Bob@123", is_admin=False),
		]
		for u in seed:
			if not crud.get_user_by_email(u.email):
				crud.create_user(u)
	except Exception as e:
		print(f"Failed to seed demo users: {e}")
		raise


def _seed_demo_subscriptions() -> None:
	if os.getenv("SEED_DEMO_SUBSCRIPTIONS", "true").lower() != "true":
		return
	try:
		from .database import get_db
		db = get_db()
		if db.subscriptions.estimated_document_count() > 0:
			return
		admin = crud.get_user_by_email("admin@demo.com")
		alice = crud.get_user_by_email("alice@demo.com")
		bob = crud.get_user_by_email("bob@demo.com")
		if not (admin and alice and bob):
			return
		# Create a few sample subscriptions
		seven_days = datetime.utcnow().replace(microsecond=0)
		samples = [
			(SubscriptionCreate(service_name="Netflix", cost=15.99, billing_cycle="monthly", renewal_date=seven_days, notes="4K plan", is_shared=True, visibility="shared"), str(admin.id)),
			(SubscriptionCreate(service_name="Spotify", cost=9.99, billing_cycle="monthly", renewal_date=seven_days, notes="", is_shared=False, visibility="private"), str(alice.id)),
			(SubscriptionCreate(service_name="Domain", cost=12.0, billing_cycle="yearly", renewal_date=seven_days, notes="example.com", is_shared=False, visibility="private"), str(bob.id)),
		]
		for sub, owner in samples:
			crud.create_subscription(sub, owner)
	except Exception as e:
		print(f"Failed to seed demo subscriptions: {e}")
		raise


# Seed demo data only if database is available
try:
    _seed_demo_users()
    _seed_demo_subscriptions()
except Exception as e:
    print(f"⚠️  Demo data seeding failed: {e}")
    print("This is normal if MongoDB is not running.")


@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
	user = auth.authenticate_user(form_data.username, form_data.password)
	if not user:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Incorrect email or password",
			headers={"WWW-Authenticate": "Bearer"},
		)
	expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
	token = auth.create_access_token(data={"sub": user.email}, expires_delta=expires)
	return {"access_token": token, "token_type": "bearer"}


# Password Reset Routes
@app.post("/auth/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
	"""Send password reset OTP to email"""
	# Check if user exists
	user = crud.get_user_by_email(request.email)
	if not user:
		# Don't reveal if email exists or not for security
		return {"message": "If the email exists, a password reset code has been sent"}
	
	# Generate and store OTP
	otp = auth.generate_otp()
	auth.store_otp(request.email, otp)
	
	# Send email
	success = auth.send_password_reset_email(request.email, otp)
	if not success:
		raise HTTPException(status_code=500, detail="Failed to send email")
	
	return {"message": "Password reset code sent to your email"}


@app.post("/auth/verify-otp")
async def verify_otp(request: VerifyOTPRequest):
	"""Verify OTP for password reset"""
	is_valid = auth.verify_otp(request.email, request.otp)
	if not is_valid:
		raise HTTPException(status_code=400, detail="Invalid or expired OTP")
	
	return {"message": "OTP verified successfully"}


@app.post("/auth/reset-password")
async def reset_password(request: ResetPasswordRequest):
	"""Reset password with OTP verification"""
	# Verify OTP first
	is_valid = auth.verify_otp(request.email, request.otp)
	if not is_valid:
		raise HTTPException(status_code=400, detail="Invalid or expired OTP")
	
	# Reset password
	success = auth.reset_password(request.email, request.new_password)
	if not success:
		raise HTTPException(status_code=500, detail="Failed to reset password")
	
	return {"message": "Password reset successfully"}


@app.get("/users/", response_model=List[User])
async def list_users_route(current_user: UserInDB = Depends(get_current_admin)):
	return crud.list_users()


@app.get("/users/me", response_model=User)
async def me(current_user: UserInDB = Depends(get_current_user)):
	return User(**current_user.model_dump(by_alias=True))


@app.post("/users/", response_model=User)
async def create_user_route(user: UserCreate, current_user: UserInDB = Depends(get_current_admin)):
	if crud.get_user_by_email(user.email):
		raise HTTPException(status_code=400, detail="Email already registered")
	return crud.create_user(user)


@app.put("/users/me/notifications")
async def update_notification_preferences(preferences: NotificationPreferences, current_user: UserInDB = Depends(get_current_user)):
	success = crud.update_user_notification_preferences(str(current_user.id), preferences)
	if not success:
		raise HTTPException(status_code=400, detail="Failed to update preferences")
	return {"message": "Preferences updated successfully"}


@app.post("/subscriptions/", response_model=Subscription)
async def create_subscription_route(subscription: SubscriptionCreate, current_user: UserInDB = Depends(get_current_user)):
	return crud.create_subscription(subscription, str(current_user.id))


@app.get("/subscriptions/", response_model=List[Subscription])
async def list_subscriptions_route(current_user: UserInDB = Depends(get_current_user), skip: int = 0, limit: int = 100):
	if current_user.is_admin:
		return crud.get_all_subscriptions(skip, limit)
	return crud.get_accessible_subscriptions(str(current_user.id), skip, limit)


@app.get("/subscriptions/upcoming", response_model=List[Subscription])
async def list_upcoming_subscriptions_route(current_user: UserInDB = Depends(get_current_user), within_days: int = 7, skip: int = 0, limit: int = 100):
	if current_user.is_admin:
		return crud.get_upcoming_subscriptions_all(within_days, skip, limit)
	return crud.get_upcoming_subscriptions_accessible(str(current_user.id), within_days, skip, limit)


@app.get("/subscriptions/{subscription_id}", response_model=Subscription)
async def get_subscription_route(subscription_id: str, current_user: UserInDB = Depends(get_current_user)):
	sub = crud.get_subscription(subscription_id)
	if not sub:
		raise HTTPException(status_code=404, detail="Subscription not found")
	if not current_user.is_admin and str(sub.owner_id) != str(current_user.id):
		raise HTTPException(status_code=403, detail="Not enough permissions")
	return sub


@app.put("/subscriptions/{subscription_id}", response_model=Subscription)
async def update_subscription_route(subscription_id: str, subscription: SubscriptionUpdate, current_user: UserInDB = Depends(get_current_user)):
	existing = crud.get_subscription(subscription_id)
	if not existing:
		raise HTTPException(status_code=404, detail="Subscription not found")
	if not current_user.is_admin and str(existing.owner_id) != str(current_user.id):
		raise HTTPException(status_code=403, detail="Not enough permissions")
	return crud.update_subscription(subscription_id, subscription)


@app.delete("/subscriptions/{subscription_id}")
async def delete_subscription_route(subscription_id: str, current_user: UserInDB = Depends(get_current_user)):
	existing = crud.get_subscription(subscription_id)
	if not existing:
		raise HTTPException(status_code=404, detail="Subscription not found")
	if not current_user.is_admin and str(existing.owner_id) != str(current_user.id):
		raise HTTPException(status_code=403, detail="Not enough permissions")
	crud.delete_subscription(subscription_id)
	return {"message": "Subscription deleted"}


@app.get("/subscriptions/{subscription_id}/insights")
async def subscription_insights_route(subscription_id: str, current_user: UserInDB = Depends(get_current_user)):
	sub = crud.get_subscription(subscription_id)
	if not sub:
		raise HTTPException(status_code=404, detail="Subscription not found")
	if not current_user.is_admin and str(sub.owner_id) != str(current_user.id):
		raise HTTPException(status_code=403, detail="Not enough permissions")
	return {"insights": ai_insights.generate_insights(sub)}


# Notification routes
@app.get("/notifications/")
async def get_notifications_route(current_user: UserInDB = Depends(get_current_user), limit: int = 50):
	notifications = crud.get_user_notifications(str(current_user.id), limit)
	return {"notifications": notifications}


@app.get("/notifications/unread-count")
async def get_unread_count_route(current_user: UserInDB = Depends(get_current_user)):
	count = crud.get_unread_notification_count(str(current_user.id))
	return {"count": count}


@app.put("/notifications/{notification_id}/read")
async def mark_notification_read_route(notification_id: str, current_user: UserInDB = Depends(get_current_user)):
	success = crud.mark_notification_read(notification_id)
	if not success:
		raise HTTPException(status_code=404, detail="Notification not found")
	return {"message": "Notification marked as read"}


@app.post("/notifications/check-renewals")
async def check_renewal_notifications_route(background_tasks: BackgroundTasks):
	"""Manually trigger renewal notification check (for testing)"""
	background_tasks.add_task(notifications.check_renewal_notifications)
	return {"message": "Renewal check initiated"}


if __name__ == "__main__":
	import uvicorn
	uvicorn.run(app, host="0.0.0.0", port=8000)
