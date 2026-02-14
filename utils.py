"""
Utility Functions for SchoolSync Pro
=====================================
Email, SMS, 2FA (TOTP), and other helper functions.

Author: SchoolSync Team
Last Updated: 2026-01-16
"""

from flask_mail import Message
from flask import current_app, url_for
import random
import string
import sys
from threading import Thread
import io
import base64
from itsdangerous import URLSafeTimedSerializer



# ============================================
# OTP GENERATION
# ============================================

def generate_otp():
    """
    Generate a random 6-digit numeric OTP code.
    
    Returns:
        str: 6-digit numeric string
    """
    return ''.join(random.choices(string.digits, k=6))


# ============================================
# EMAIL FUNCTIONS
# ============================================

def send_async_email(app, msg):
    """
    Send email asynchronously in background thread.
    
    Args:
        app: Flask application instance
        msg: Flask-Mail Message object
    """
    with app.app_context():
        try:
            from extensions import mail
            mail.send(msg)
            print("✅ Email sent successfully", file=sys.stdout)
        except Exception as e:
            print(f"❌ Email failed: {str(e)}", file=sys.stderr)


def send_email_otp(email, otp):
    """
    Send OTP verification code via email.
    
    Args:
        email (str): Recipient email address
        otp (str): 6-digit OTP code
        
    Returns:
        bool: True (always, to not break flow even if email fails)
    """
    try:
        msg = Message(
            'SchoolSync Login Verification',
            recipients=[email]
        )
        msg.body = f'''Your SchoolSync verification code is:

{otp}

This code will expire in 10 minutes.

If you did not request this code, please ignore this email.

---
SchoolSync Pro - Student Management System
'''
        
        app = current_app._get_current_object()
        thread = Thread(target=send_async_email, args=[app, msg])
        thread.start()
        
        print(f"📧 Sending OTP to {email}...", file=sys.stdout)
        return True
        
    except Exception as e:
        print(f"❌ Error starting email task: {e}", file=sys.stderr)
        return True  # Don't break login flow


def send_password_reset_email(email):
    """
    Send password reset link via email.
    
    Generates signed token with 1-hour expiration.
    
    Args:
        email (str): Recipient email address
        
    Returns:
        bool: True if email queued, False on error
    """
    try:
        # Generate secure token
        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        token = serializer.dumps(email, salt='password-reset-salt')
        
        # Create password reset link
        link = url_for('auth.reset_password', token=token, _external=True)
        
        # Create email message
        msg = Message(
            'Reset Your Password - SchoolSync Pro',
            recipients=[email]
        )
        msg.body = f'''Hello,

You requested to reset your SchoolSync Pro password.

Click the link below to reset your password:
{link}

This link will expire in 1 hour.

If you did not request a password reset, please ignore this email. 
No changes will be made to your account.

---
SchoolSync Pro - Student Management System
'''
        
        # Send asynchronously
        app = current_app._get_current_object()
        thread = Thread(target=send_async_email, args=[app, msg])
        thread.start()
        
        print(f"📧 Sending password reset to {email}...", file=sys.stdout)
        print(f"🔐 [DEBUG] Reset link: {link}", file=sys.stdout)
        
        return True
        
    except Exception as e:
        print(f"❌ Error generating reset link: {e}", file=sys.stderr)
        return False


# ============================================
# SMS FUNCTIONS (TWILIO)
# ============================================

def send_sms_otp(phone, otp):
    """
    Send OTP verification code via SMS (Twilio).
    
    Falls back to mock/logging if Twilio is not configured.
    
    Args:
        phone (str): Recipient phone number
        otp (str): 6-digit OTP code
        
    Returns:
        bool: True (always, to not break flow)
    """
    try:
        account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
        auth_token = current_app.config.get('TWILIO_AUTH_TOKEN')
        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')

        # Check if Twilio is configured
        if not account_sid or not auth_token or not from_number:
            print(
                f"📱 [MOCK SMS] To: {phone} | Code: {otp}",
                file=sys.stdout
            )
            return True

        # Send real SMS via Twilio
        from twilio.rest import Client
        
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=f"Your SchoolSync verification code is: {otp}\n\nExpires in 10 minutes.",
            from_=from_number,
            to=phone
        )
        
        print(f"📱 SMS sent to {phone} (SID: {message.sid})", file=sys.stdout)
        return True
        
    except Exception as e:
        print(f"❌ SMS failed: {e}", file=sys.stderr)
        return True  # Don't break login flow


# ============================================
# TOTP (GOOGLE AUTHENTICATOR) FUNCTIONS
# ============================================

def get_totp_uri(user):
    """
    Generate TOTP URI for QR code (Google Authenticator setup).
    
    Creates a standard otpauth:// URI that can be scanned by
    authenticator apps like Google Authenticator or Authy.
    
    Args:
        user: User model instance with totp_secret
        
    Returns:
        tuple: (uri_string, secret) or (None, None) if no secret
    """
    if not user.totp_secret:
        return None, None
    
    try:
        totp = pyotp.TOTP(user.totp_secret)
        
        # Clean username (remove spaces and special characters)
        clean_username = user.username.replace(" ", "").replace("@", "_")
        
        # Generate standard TOTP URI
        # Format: otpauth://totp/Issuer:Account?secret=SECRET&issuer=Issuer
        uri = totp.provisioning_uri(
            name=clean_username,
            issuer_name="SchoolSync Pro"
        )
        
        print(f"🔑 Generated 2FA URI for {user.username}", file=sys.stdout)
        return uri, user.totp_secret
        
    except Exception as e:
        print(f"❌ Error generating TOTP URI: {e}", file=sys.stderr)
        return None, None


def generate_qr_code(uri):
    """
    Convert TOTP URI to QR code image (Base64 PNG).
    
    Args:
        uri (str): TOTP URI from get_totp_uri()
        
    Returns:
        str: Base64-encoded PNG image as data URI
    """
    try:
        import qrcode
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)

        # Generate image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to Base64
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        return f"data:image/png;base64,{img_str}"
        
    except Exception as e:
        print(f"❌ Error generating QR code: {e}", file=sys.stderr)
        return None


def verify_totp(user, code):
    """
    Verify TOTP code from authenticator app.
    
    Args:
        user: User model instance with totp_secret
        code (str): 6-digit code from authenticator app
        
    Returns:
        bool: True if code is valid, False otherwise
    """
    if not user.totp_secret:
        return False
    
    try:
        totp = pyotp.TOTP(user.totp_secret)
        
        # Verify with window of ±1 period (30 seconds each)
        # This allows for slight time drift
        is_valid = totp.verify(code, valid_window=1)
        
        if is_valid:
            print(f"✅ TOTP verified for {user.username}", file=sys.stdout)
        else:
            print(f"❌ Invalid TOTP for {user.username}", file=sys.stdout)
        
        return is_valid
        
    except Exception as e:
        print(f"❌ TOTP verification error: {e}", file=sys.stderr)
        return False


# ============================================
# TOKEN GENERATION HELPERS
# ============================================

def generate_secure_token(data, salt='default-salt', max_age=3600):
    """
    Generate secure signed token with expiration.
    
    Args:
        data: Data to encode in token (usually email or user ID)
        salt (str): Salt for token signing
        max_age (int): Token lifetime in seconds
        
    Returns:
        str: Signed token
    """
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(data, salt=salt)


def verify_secure_token(token, salt='default-salt', max_age=3600):
    """
    Verify and decode secure token.
    
    Args:
        token (str): Token to verify
        salt (str): Salt used during signing
        max_age (int): Maximum age in seconds
        
    Returns:
        tuple: (success: bool, data or error_message)
    """
    try:
        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        data = serializer.loads(token, salt=salt, max_age=max_age)
        return True, data
    except Exception as e:
        return False, str(e)


# ============================================
# AUTOMATION (n8n)
# ============================================

def send_to_n8n(event_type, payload):
    """
    Send data to n8n webhook for automated workflows.
    
    Args:
        event_type (str): Type of event (e.g., 'student_enrolled', 'grade_updated')
        payload (dict): The data to send
    """
    from flask import current_app
    from datetime import datetime
    
    webhook_url = current_app.config.get('N8N_WEBHOOK_URL')
    if not webhook_url:
        return False

    def trigger_webhook(url, body):
        try:
            import requests
            # Standard n8n body structure
            n8n_data = {
                'event': event_type,
                'data': body,
                'timestamp': datetime.utcnow().isoformat()
            }
            response = requests.post(url, json=n8n_data, timeout=5)
            if response.status_code >= 200 and response.status_code < 300:
                print(f"🚀 n8n Webhook Triggered: {event_type}")
            else:
                print(f"⚠️ n8n Webhook returned status: {response.status_code}")
        except Exception as e:
            print(f"❌ n8n Webhook error: {str(e)}")

    # Run in background to not slow down the user request
    thread = Thread(target=trigger_webhook, args=[webhook_url, payload])
    thread.start()
    return True
