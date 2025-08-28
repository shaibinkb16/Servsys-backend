import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import EmailStr

from .database import get_db
from .models import UserInDB
from .notifications import send_email_notification

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# OTP settings
OTP_EXPIRE_MINUTES = 10
OTP_LENGTH = 6

def verify_password(plain_password: str, hashed_password: str) -> bool:
	return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
	return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
	to_encode = data.copy()
	if expires_delta:
		expire = datetime.utcnow() + expires_delta
	else:
		expire = datetime.utcnow() + timedelta(minutes=15)
	to_encode.update({"exp": expire})
	encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
	return encoded_jwt

def verify_token(token: str) -> Optional[str]:
	try:
		payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
		email: str = payload.get("sub")
		if email is None:
			return None
		return email
	except JWTError:
		return None

def authenticate_user(email: str, password: str) -> Optional[UserInDB]:
	db = get_db()
	user_data = db.users.find_one({"email": email})
	if not user_data:
		return None
	
	user = UserInDB(**user_data)
	if not verify_password(password, user.hashed_password):
		return None
	return user

def get_current_user(token: str) -> UserInDB:
	credentials_exception = HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="Could not validate credentials",
		headers={"WWW-Authenticate": "Bearer"},
	)
	
	email = verify_token(token)
	if email is None:
		raise credentials_exception
	
	db = get_db()
	user_data = db.users.find_one({"email": email})
	if user_data is None:
		raise credentials_exception
	
	return UserInDB(**user_data)

def generate_otp() -> str:
	"""Generate a 6-digit OTP"""
	return ''.join(secrets.choice('0123456789') for _ in range(OTP_LENGTH))

def store_otp(email: str, otp: str) -> None:
	"""Store OTP in database with expiration"""
	db = get_db()
	expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRE_MINUTES)
	
	# Remove any existing OTP for this email
	db.password_resets.delete_many({"email": email})
	
	# Store new OTP
	db.password_resets.insert_one({
		"email": email,
		"otp": otp,
		"expires_at": expires_at,
		"created_at": datetime.utcnow()
	})

def verify_otp(email: str, otp: str) -> bool:
	"""Verify OTP and return True if valid"""
	db = get_db()
	reset_data = db.password_resets.find_one({
		"email": email,
		"otp": otp,
		"expires_at": {"$gt": datetime.utcnow()}
	})
	
	if reset_data:
		# Remove the used OTP
		db.password_resets.delete_one({"_id": reset_data["_id"]})
		return True
	return False

def send_password_reset_email(email: str, otp: str) -> bool:
	"""Send password reset email with OTP"""
	subject = "Password Reset - Subscription Manager"
	html_content = f"""
	<!DOCTYPE html>
	<html>
	<head>
		<style>
			body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
			.container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
			.header {{ background: linear-gradient(135deg, #7758D1 0%, #F7CBF9 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
			.content {{ padding: 30px; background: #f9f9f9; border-radius: 0 0 10px 10px; }}
			.otp-box {{ background: white; padding: 20px; margin: 20px 0; text-align: center; border-radius: 10px; border: 2px solid #7758D1; }}
			.otp-code {{ font-size: 32px; font-weight: bold; color: #7758D1; letter-spacing: 5px; }}
			.button {{ display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #7758D1 0%, #F7CBF9 100%); color: white; text-decoration: none; border-radius: 8px; margin: 20px 0; }}
			.footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
		</style>
	</head>
	<body>
		<div class="container">
			<div class="header">
				<h1>🔐 Password Reset</h1>
				<p>Subscription Manager</p>
			</div>
			<div class="content">
				<p>Hello,</p>
				<p>We received a request to reset your password for your Subscription Manager account.</p>
				
				<div class="otp-box">
					<p><strong>Your verification code is:</strong></p>
					<div class="otp-code">{otp}</div>
					<p style="font-size: 14px; color: #666;">This code will expire in 10 minutes</p>
				</div>
				
				<p>If you didn't request this password reset, please ignore this email.</p>
				
				<p>Best regards,<br>Subscription Manager Team</p>
			</div>
			<div class="footer">
				<p>This is an automated email. Please do not reply.</p>
			</div>
		</div>
	</body>
	</html>
	"""
	
	return send_email_notification(email, subject, html_content)

def reset_password(email: str, new_password: str) -> bool:
	"""Reset user password"""
	db = get_db()
	hashed_password = get_password_hash(new_password)
	
	result = db.users.update_one(
		{"email": email},
		{"$set": {"hashed_password": hashed_password}}
	)
	
	return result.modified_count > 0
