import os
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from jinja2 import Template
from dotenv import load_dotenv

from .database import get_db
from .models import Notification, Subscription, User

load_dotenv()

# Email configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@subscriptionmanager.com")

# Email templates
RENEWAL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #4F46E5; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; background: #f9f9f9; }
        .subscription { background: white; padding: 15px; margin: 10px 0; border-left: 4px solid #4F46E5; }
        .button { display: inline-block; padding: 10px 20px; background: #4F46E5; color: white; text-decoration: none; border-radius: 5px; }
        .footer { text-align: center; padding: 20px; color: #666; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔔 Subscription Renewal Reminder</h1>
        </div>
        <div class="content">
            <p>Hello {{ user_email }},</p>
            <p>You have subscription(s) renewing soon:</p>
            
            {% for sub in subscriptions %}
            <div class="subscription">
                <h3>{{ sub.service_name }}</h3>
                <p><strong>Cost:</strong> ${{ sub.cost }} per {{ sub.billing_cycle }}</p>
                <p><strong>Renews on:</strong> {{ sub.renewal_date.strftime('%B %d, %Y') }}</p>
                <p><strong>Days until renewal:</strong> {{ sub.days_until }}</p>
                {% if sub.notes %}
                <p><strong>Notes:</strong> {{ sub.notes }}</p>
                {% endif %}
            </div>
            {% endfor %}
            
            <p style="margin-top: 20px;">
                <a href="{{ dashboard_url }}" class="button">View Dashboard</a>
            </p>
        </div>
        <div class="footer">
            <p>This is an automated reminder from your Subscription Manager.</p>
            <p>You can manage your notification preferences in your account settings.</p>
        </div>
    </div>
</body>
</html>
"""


def send_email_notification(to_email: str, subject: str, html_content: str) -> bool:
	"""Send email notification using SMTP."""
	if not all([SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL]):
		print("Email configuration incomplete. Skipping email notification.")
		return False
	
	try:
		msg = MIMEMultipart('alternative')
		msg['Subject'] = subject
		msg['From'] = FROM_EMAIL
		msg['To'] = to_email
		
		html_part = MIMEText(html_content, 'html')
		msg.attach(html_part)
		
		with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
			server.starttls()
			server.login(SMTP_USERNAME, SMTP_PASSWORD)
			server.send_message(msg)
		
		print(f"Email notification sent to {to_email}")
		return True
	except Exception as e:
		print(f"Failed to send email notification: {e}")
		return False


def create_browser_notification(user_id: str, subscription_id: str, message: str, notification_type: str) -> Notification:
	"""Create a browser notification record."""
	db = get_db()
	notification = {
		"user_id": user_id,
		"subscription_id": subscription_id,
		"message": message,
		"type": notification_type,
		"is_read": False,
		"created_at": datetime.utcnow()
	}
	result = db.notifications.insert_one(notification)
	created = db.notifications.find_one({"_id": result.inserted_id})
	return Notification(**created)


def get_user_notifications(user_id: str, limit: int = 50) -> List[Notification]:
	"""Get notifications for a user."""
	db = get_db()
	cursor = db.notifications.find({"user_id": user_id}).sort("created_at", -1).limit(limit)
	return [Notification(**doc) for doc in cursor]


def mark_notification_read(notification_id: str) -> bool:
	"""Mark a notification as read."""
	db = get_db()
	result = db.notifications.update_one(
		{"_id": notification_id},
		{"$set": {"is_read": True}}
	)
	return result.modified_count > 0


def check_renewal_notifications() -> None:
	"""Check for subscriptions that need renewal notifications."""
	db = get_db()
	now = datetime.utcnow()
	
	# Get all users with their notification preferences
	users = db.users.find()
	
	for user_doc in users:
		user = User(**user_doc)
		prefs = user.notification_preferences or {}
		reminder_days = prefs.get("reminder_days", [1, 3, 7])
		
		# Check each reminder day
		for days in reminder_days:
			target_date = now + timedelta(days=days)
			start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
			end_of_day = start_of_day + timedelta(days=1)
			
			# Find subscriptions renewing on this day
			subscriptions = db.subscriptions.find({
				"owner_id": user.id,
				"renewal_date": {"$gte": start_of_day, "$lt": end_of_day},
				"$or": [
					{"last_notified": {"$exists": False}},
					{"last_notified": {"$lt": start_of_day}}
				]
			})
			
			for sub_doc in subscriptions:
				subscription = Subscription(**sub_doc)
				
				# Create browser notification
				message = f"{subscription.service_name} renews in {days} day(s) - ${subscription.cost}"
				create_browser_notification(
					str(user.id),
					str(subscription.id),
					message,
					"renewal_reminder"
				)
				
				# Send email if enabled
				if prefs.get("email_notifications", True):
					send_renewal_email(user, [subscription], days)
				
				# Update last_notified
				db.subscriptions.update_one(
					{"_id": subscription.id},
					{"$set": {"last_notified": now}}
				)


def send_renewal_email(user: User, subscriptions: List[Subscription], days_until: int) -> None:
	"""Send renewal reminder email."""
	template = Template(RENEWAL_TEMPLATE)
	
	# Prepare subscription data for template
	sub_data = []
	for sub in subscriptions:
		sub_data.append({
			"service_name": sub.service_name,
			"cost": sub.cost,
			"billing_cycle": sub.billing_cycle,
			"renewal_date": sub.renewal_date,
			"days_until": days_until,
			"notes": sub.notes
		})
	
	html_content = template.render(
		user_email=user.email,
		subscriptions=sub_data,
		dashboard_url="http://localhost:5173"  # Update with actual URL
	)
	
	send_email_notification(
		user.email,
		f"Subscription Renewal Reminder - {days_until} day(s)",
		html_content
	)


def get_unread_notification_count(user_id: str) -> int:
	"""Get count of unread notifications for a user."""
	db = get_db()
	return db.notifications.count_documents({
		"user_id": user_id,
		"is_read": False
	})


def delete_old_notifications(days_old: int = 30) -> int:
	"""Delete notifications older than specified days."""
	db = get_db()
	cutoff_date = datetime.utcnow() - timedelta(days=days_old)
	result = db.notifications.delete_many({
		"created_at": {"$lt": cutoff_date}
	})
	return result.deleted_count 