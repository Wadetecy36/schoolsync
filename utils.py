from flask_mail import Message
from flask import current_app
import random
import string
from twilio.rest import Client
import sys
from threading import Thread

def generate_otp():
    """Generate a 6-digit numeric code"""
    return ''.join(random.choices(string.digits, k=6))

# --- Helper to send email in background ---
def send_async_email(app, msg):
    with app.app_context():
        try:
            from app import mail
            mail.send(msg)
            print("✅ Background Email sent successfully!", file=sys.stdout)
        except Exception as e:
            print(f"❌ Background Email Failed: {str(e)}", file=sys.stderr)

def send_email_otp(email, otp):
    """Send OTP via Email (Non-blocking)"""
    try:
        # Create message
        msg = Message('SchoolSync Login Verification', recipients=[email])
        msg.body = f'Your verification code is: {otp}\n\nThis code expires in 10 minutes.'
        
        # CRITICAL FIX: Send in a background thread
        # This prevents the "SIGKILL" timeout error on Render
        app = current_app._get_current_object()
        thread = Thread(target=send_async_email, args=[app, msg])
        thread.start()
        
        print(f"📧 Email task started for {email}...", file=sys.stdout)
        
        # Print backup code just in case email fails completely
        print(f"🔓 [EMERGENCY BACKUP] OTP: {otp}", file=sys.stdout)
        
        return True
        
    except Exception as e:
        print(f"❌ Error starting email task: {e}", file=sys.stderr)
        return True # Return True anyway to let user proceed

def send_sms_otp(phone, otp):
    """Send OTP via SMS (Twilio)"""
    try:
        account = current_app.config.get('TWILIO_ACCOUNT_SID')
        token = current_app.config.get('TWILIO_AUTH_TOKEN')
        number = current_app.config.get('TWILIO_PHONE_NUMBER')

        if not account or not token or not number:
            print(f"📱 [MOCK SMS] To: {phone} | Code: {otp}", file=sys.stdout)
            return True

        client = Client(account, token)
        client.messages.create(
            body=f"Your SchoolSync code is: {otp}",
            from_=number,
            to=phone
        )
        return True
    except Exception as e:
        print(f"❌ SMS FAILED: {e}", file=sys.stderr)
        print(f"🔓 [EMERGENCY BACKUP] OTP: {otp}", file=sys.stdout)
        return True