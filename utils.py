from flask_mail import Message
from flask import current_app, url_for
import random
import string
from twilio.rest import Client
import sys
from threading import Thread
from itsdangerous import URLSafeTimedSerializer
import pyotp
import qrcode
import io
import base64

def generate_otp():
    """Generate a 6-digit numeric code"""
    return ''.join(random.choices(string.digits, k=6))

# --- Async Email Sender ---
def send_async_email(app, msg):
    with app.app_context():
        try:
            from app import mail
            mail.send(msg)
            print("✅ Background Email sent successfully!", file=sys.stdout)
        except Exception as e:
            print(f"❌ Background Email Failed: {str(e)}", file=sys.stderr)

# --- OTP Email ---
def send_email_otp(email, otp):
    try:
        msg = Message('SchoolSync Login Verification', recipients=[email])
        msg.body = f'Your verification code is: {otp}\n\nThis code expires in 10 minutes.'
        
        app = current_app._get_current_object()
        thread = Thread(target=send_async_email, args=[app, msg])
        thread.start()
        
        print(f"📧 Sending OTP to {email}...", file=sys.stdout)
        return True
    except Exception as e:
        print(f"❌ Error starting email task: {e}", file=sys.stderr)
        return True


# --- GOOGLE AUTHENTICATOR HELPERS ---

def get_totp_uri(user):
    """Generate the URL for the QR Code"""
    # 1. Generate a random secret if user doesn't have one
    if not user.totp_secret:
        return None, None
        
    totp = pyotp.TOTP(user.totp_secret)
    # This creates the link that the QR code stores
    uri = totp.provisioning_uri(name=user.username, issuer_name="SchoolSync Pro")
    return uri, user.totp_secret

def generate_qr_code(uri):
    """Convert the URI into a PNG image string"""
    qr = qrcode.make(uri)
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    # Encode as Base64 to show in HTML
    img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{img_str}"

def verify_totp(user, code):
    """Check if the code from the App is correct"""
    if not user.totp_secret:
        return False
    totp = pyotp.TOTP(user.totp_secret)
    return totp.verify(code)

# --- NEW: Password Reset Email ---
def send_password_reset_email(email):
    try:
        # Generate Token
        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        token = serializer.dumps(email, salt='password-reset-salt')
        
        # Create Link
        link = url_for('auth.reset_password', token=token, _external=True)
        
        msg = Message('Reset Your Password - SchoolSync Pro', recipients=[email])
        msg.body = f'''To reset your password, visit the following link:
{link}

If you did not make this request then simply ignore this email and no changes will be made.
This link expires in 1 hour.
'''
        app = current_app._get_current_object()
        thread = Thread(target=send_async_email, args=[app, msg])
        thread.start()
        
        print(f"📧 Sending Password Reset to {email}...", file=sys.stdout)
        # Debug link for Render logs in case email fails
        print(f"🔐 [DEBUG LINK]: {link}", file=sys.stdout) 
        return True
    except Exception as e:
        print(f"❌ Error generating reset link: {e}", file=sys.stderr)
        return False

# --- SMS (Existing) ---
def send_sms_otp(phone, otp):
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
        return True