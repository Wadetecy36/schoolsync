from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
from datetime import datetime, timedelta
# Import verify_totp for the App 2FA logic
from utils import generate_otp, send_email_otp, send_password_reset_email, verify_totp 
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import re

auth = Blueprint('auth', __name__)

@auth.before_request
def make_session_permanent():
    """Make session permanent with timeout"""
    session.permanent = True

# ================================
# LOGIN & 2FA LOGIC
# ================================

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        password = data.get('password', '')
        remember = data.get('remember') == 'on' or data.get('remember') is True
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Account is disabled.', 'error')
                return redirect(url_for('auth.login'))

            # --- 2FA CHECK ---
            if user.two_factor_method in ['email', 'app']:
                session['2fa_user_id'] = user.id
                session['remember_me'] = remember
                
                # Case 1: Authenticator App (Google/Authy)
                if user.two_factor_method == 'app':
                    flash('Enter the 6-digit code from your Authenticator App.', 'info')
                
                # Case 2: Email OTP
                elif user.two_factor_method == 'email':
                    otp = generate_otp()
                    user.otp_code = otp
                    user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
                    db.session.commit()
                    
                    send_email_otp(user.email, otp)
                    flash(f'Verification code sent to {user.email}', 'info')
                
                if request.is_json:
                    return jsonify({'success': True, 'redirect': url_for('auth.verify_2fa')})
                return redirect(url_for('auth.verify_2fa'))

            # --- NO 2FA (Direct Login) ---
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user, remember=remember)
            
            if request.is_json:
                return jsonify({'success': True, 'redirect': url_for('main.index')})
            return redirect(url_for('main.index'))
            
        # Failed Login
        flash('Invalid username or password', 'error')
        if request.is_json:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

    return render_template('login.html')

@auth.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa():
    """2FA Verification Step"""
    user_id = session.get('2fa_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        code = request.form.get('otp_code', '').strip()
        verified = False

        # Check App (TOTP)
        if user.two_factor_method == 'app':
            if verify_totp(user, code):
                verified = True
            else:
                flash('Invalid Authenticator code.', 'error')

        # Check Email (Database OTP)
        elif user.two_factor_method == 'email':
            if user.otp_code == code and user.otp_expiry > datetime.utcnow():
                verified = True
            elif user.otp_code != code:
                flash('Invalid code. Please check your email.', 'error')
            else:
                flash('Code has expired. Please log in again.', 'warning')
                return redirect(url_for('auth.login'))
        
        # Complete Login if Verified
        if verified:
            try:
                user.otp_code = None
                user.otp_expiry = None
                user.last_login = datetime.utcnow()
                db.session.commit()
                
                remember = session.get('remember_me', False)
                session.pop('2fa_user_id', None)
                session.pop('remember_me', None)
                
                login_user(user, remember=remember)
                return redirect(url_for('main.index'))
            except Exception as e:
                db.session.rollback()
                flash(f'System error: {str(e)}', 'error')
                return redirect(url_for('auth.login'))
            
    return render_template('verify_2fa.html', method=user.two_factor_method)

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('auth.login'))

@auth.route('/register', methods=['GET', 'POST'])
def register():
    """Register new admin"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        # Your logic here or keeping it closed/manual only
        pass
    return render_template('register.html')

# ================================
# PASSWORD RESET ROUTES
# ================================

@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        email = request.form.get('email').strip()
        user = User.query.filter_by(email=email).first()
        
        # Security: Always flash success to prevent email enumeration
        if user:
            send_password_reset_email(user.email)
        
        flash('If that email is registered, we have sent password reset instructions.', 'info')
        return redirect(url_for('auth.login'))
            
    return render_template('forgot_password.html')

@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    try:
        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        # 1 Hour Expiration
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600) 
    except SignatureExpired:
        flash('The reset link has expired.', 'error')
        return redirect(url_for('auth.forgot_password'))
    except BadSignature:
        flash('Invalid reset link.', 'error')
        return redirect(url_for('auth.forgot_password'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')
        
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)
            
        user = User.query.filter_by(email=email).first()
        if user:
            try:
                user.set_password(password)
                db.session.commit()
                flash('Your password has been updated! You can now log in.', 'success')
                return redirect(url_for('auth.login'))
            except ValueError as e:
                flash(str(e), 'error')
                
    return render_template('reset_password.html', token=token)