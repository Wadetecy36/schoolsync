from flask_mail import Message
from flask import current_app
import random
import string
from twilio.rest import Client
import logging

def generate_otp():
    """Generate a 6-digit numeric code"""
    return ''.join(random.choices(string.digits, k=6))

def send_email_otp(email, otp):
    """Send OTP via Email"""
    from app import mail # Import here to avoid circular dependency
    try:
        msg = Message('Your Login Verification Code',
                      recipients=[email])
        msg.body = f'Your verification code is: {otp}\n\nThis code expires in 10 minutes.'
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send email OTP: {e}")
        return False

def send_sms_otp(phone, otp):
    """Send OTP via SMS (Twilio)"""
    # 1. MOCK MODE (For testing without API keys)
    if not current_app.config.get('TWILIO_ACCOUNT_SID'):
        print(f"\n[MOCK SMS] To: {phone} | Code: {otp}\n")
        current_app.logger.info(f"Mock SMS sent to {phone}: {otp}")
        return True

    # 2. REAL MODE
    try:
        client = Client(current_app.config['TWILIO_ACCOUNT_SID'], 
                        current_app.config['TWILIO_AUTH_TOKEN'])
        
        message = client.messages.create(
            body=f"Your SchoolSync code is: {otp}",
            from_=current_app.config['TWILIO_PHONE_NUMBER'],
            to=phone
        )
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send SMS OTP: {e}")
        return False