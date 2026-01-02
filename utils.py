from flask_mail import Message
from flask import current_app, url_for
import random
import string
from twilio.rest import Client
import sys
from threading import Thread
import pyotp
import qrcode
import io
import base64
from itsdangerous import URLSafeTimedSerializer

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

# --- TOTP (Google Authenticator) HELPERS ---
def get_totp_uri(user):
    """Generate a strict, clean otpauth URL"""
    if not user.totp_secret:
        return None, None
        
    totp = pyotp.TOTP(user.totp_secret)
    
    # FIX: Remove spaces/special chars from issuer/name to prevent parsing errors
    clean_username = user.username.replace(" ", "")
    
    # Manually build string to ensure 100% standard format
    # Format: otpauth://totp/Issuer:Account?secret=SECRET&issuer=Issuer
    uri = totp.provisioning_uri(name=clean_username, issuer_name="SchoolSync Pro")
    
    print(f"🔑 Generated 2FA URI: {uri}", file=sys.stdout) # Debug logging
    return uri, user.totp_secret

def generate_qr_code(uri):
    """Convert the URI into a PNG image string"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{img_str}"

def verify_totp(user, code):
    """Check if the code from the App is correct"""
    if not user.totp_secret:
        return False
    return pyotp.TOTP(user.totp_secret).verify(code)

# --- Password Reset Email ---
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

# --- SMS ---
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