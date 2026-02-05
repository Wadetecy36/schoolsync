"""
Authentication Module for SchoolSync Pro
=========================================
Handles user authentication, 2FA, password reset, and security logging.

Author:SchoolSync Team
Last Updated: 2026-01-16
"""

from flask import (
    Blueprint, render_template, request, redirect, url_for, 
    flash, jsonify, session, current_app
)
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db, limiter
from models import User, UsedPasswordResetToken
from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import re

# Import utilities
from utils import generate_otp, send_email_otp, send_password_reset_email, verify_totp
from security_logger import (
    log_successful_login, log_failed_login, log_logout,
    log_password_change, get_client_ip
)
import security_logger as sec_log

# Create Blueprint
auth = Blueprint('auth', __name__)


# ============================================
# SESSION MANAGEMENT
# ============================================

@auth.before_request
def make_session_permanent():
    """
    Make all sessions permanent with configured timeout.
    
    Sessions will expire after PERMANENT_SESSION_LIFETIME (default: 1 hour).
    """
    session.permanent = True


# ============================================
# LOGIN & 2FA LOGIC
# ============================================

@auth.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")  # Rate limit: max 10 login attempts per minute
def login():
    """
    User login endpoint with 2FA support.
    
    Supports:
    - Password authentication
    - Email OTP 2FA
    - TOTP (Google Authenticator) 2FA
    - Security logging
    """
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        password = data.get('password', '')
        remember = data.get('remember') == 'on' or data.get('remember') is True
        
        # Find user
        user = User.query.filter_by(username=username).first()
        
        # Verify password
        if user and user.check_password(password):
            # Check if account is active
            if not user.is_active:
                log_failed_login(username, 'Account disabled')
                flash('Account is disabled. Contact administrator.', 'error')
                return redirect(url_for('auth.login'))

            # ============================================
            # 2FA CHECK
            # ============================================
            
            if user.two_factor_method in ['email', 'app', 'sms']:
                session['2fa_user_id'] = user.id
                session['remember_me'] = remember
                
                # Case 1: Authenticator App (TOTP)
                if user.two_factor_method == 'app':
                    flash('Enter the 6-digit code from your Authenticator App.', 'info')
                
                # Case 2: Email OTP
                elif user.two_factor_method == 'email':
                    # Generate and send OTP
                    otp = generate_otp()
                    user.otp_code = otp
                    user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
                    db.session.commit()
                    
                    send_email_otp(user.email, otp)
                    flash(f'Verification code sent to {user.email}', 'info')
                
                # Case 3: SMS OTP (if configured)
                elif user.two_factor_method == 'sms':
                    from utils import send_sms_otp
                    otp = generate_otp()
                    user.otp_code = otp
                    user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
                    db.session.commit()
                    
                    send_sms_otp(user.phone, otp)
                    flash(f'Verification code sent to {user.phone}', 'info')
                
                # Redirect to 2FA verification
                if request.is_json:
                    return jsonify({'success': True, 'redirect': url_for('auth.verify_2fa')})
                return redirect(url_for('auth.verify_2fa'))

            # ============================================
            # NO 2FA (Direct Login)
            # ============================================
            
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user, remember=remember)
            
            # Log successful login
            log_successful_login(user.id, user.username, method='password')
            
            flash(f'Welcome back, {user.full_name or user.username}!', 'success')
            
            if request.is_json:
                return jsonify({'success': True, 'redirect': url_for('main.index')})
            return redirect(url_for('main.index'))
        
        # ============================================
        # FAILED LOGIN
        # ============================================
        
        log_failed_login(username, 'Invalid credentials')
        flash('Invalid username or password', 'error')
        
        if request.is_json:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

    return render_template('login.html')


@auth.route('/verify-2fa', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # Rate limit: 5 attempts per minute
def verify_2fa():
    """
    Two-factor authentication verification endpoint.
    
    Verifies OTP codes from email, SMS, or authenticator apps.
    """
    user_id = session.get('2fa_user_id')
    if not user_id:
        flash('Session expired. Please login again.', 'warning')
        return redirect(url_for('auth.login'))
    
    user = User.query.get(user_id)
    if not user:
        flash('Invalid session. Please login again.', 'error')
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        code = request.form.get('otp_code', '').strip()
        verified = False

        # ============================================
        # VERIFY TOTP (Authenticator App)
        # ============================================
        
        if user.two_factor_method == 'app':
            if verify_totp(user, code):
                verified = True
            else:
                log_failed_login(user.username, '2FA App code invalid')
                flash('Invalid Authenticator code. Please try again.', 'error')

        # ============================================
        # VERIFY EMAIL/SMS OTP
        # ============================================
        
        elif user.two_factor_method in ['email', 'sms']:
            if not user.otp_code or not user.otp_expiry:
                flash('No verification code found. Please login again.', 'warning')
                return redirect(url_for('auth.login'))
            
            if user.otp_expiry < datetime.utcnow():
                log_failed_login(user.username, '2FA OTP expired')
                flash('Verification code has expired. Please login again.', 'warning')
                session.pop('2fa_user_id', None)
                session.pop('remember_me', None)
                return redirect(url_for('auth.login'))
            
            if user.otp_code == code:
                verified = True
            else:
                log_failed_login(user.username, '2FA OTP invalid')
                flash('Invalid verification code. Please check your message.', 'error')
        
        # ============================================
        # COMPLETE LOGIN IF VERIFIED
        # ============================================
        
        if verified:
            try:
                # Clear OTP data
                user.otp_code = None
                user.otp_expiry = None
                user.last_login = datetime.utcnow()
                db.session.commit()
                
                # Get remember me preference
                remember = session.get('remember_me', False)
                session.pop('2fa_user_id', None)
                session.pop('remember_me', None)
                
                # Log user in
                login_user(user, remember=remember)
                
                # Log successful 2FA login
                method = f"2fa_{user.two_factor_method}"
                log_successful_login(user.id, user.username, method=method)
                
                flash(f'Welcome back, {user.full_name or user.username}!', 'success')
                return redirect(url_for('main.index'))
                
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"2FA login error: {e}")
                flash('An error occurred. Please try again.', 'error')
                return redirect(url_for('auth.login'))
    
    return render_template('verify_2fa.html', method=user.two_factor_method)

from flask import Blueprint, redirect, url_for, flash, session
from flask_login import login_required, logout_user, current_user
# Make sure log_logout is imported if you use it!
# from utils import log_logout 

@auth.route('/logout')
@login_required
def logout():
    """
    User logout endpoint.
    """
    try:
        # Capture info before logging out
        user_id = current_user.id
        username = current_user.username
        
        # Try to log the event, but don't stop logout if it fails
        # Ensure log_logout is actually imported!
        if 'log_logout' in globals(): 
            log_logout(user_id, username)
            
    except Exception as e:
        print(f"Error logging logout event: {e}")

    # Perform logout regardless of logging success
    logout_user()
    session.clear()
    
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('auth.login'))
    
# REGISTRATION (Currently Disabled)
# ============================================

@auth.route('/register', methods=['GET', 'POST'])
def register():
    """
    User registration endpoint (currently administrative only).
    
    In production, user accounts should be created by administrators.
    This route is kept for future self-registration features.
    """
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        flash('Self-registration is currently disabled. Contact an administrator.', 'info')
        return redirect(url_for('auth.login'))
    
    return render_template('register.html')


# ============================================
# PASSWORD RESET ROUTES
# ============================================

@auth.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("3 per hour")  # Rate limit: 3 reset requests per hour
def forgot_password():
    """
    Password reset request endpoint.
    
    Sends password reset link to user's email.
    Uses email enumeration protection.
    """
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()
        
        # Security: Always show success message (prevent email enumeration)
        if user and user.is_active:
            send_password_reset_email(user.email)
            
            # Log password reset request
            sec_log.log_security_event(
                user.id,
                sec_log.EVENT_PASSWORD_RESET_REQUEST,
                details=f"Reset link sent to {email}"
            )
        
        flash(
            'If that email is registered, we have sent password reset instructions.',
            'info'
        )
        return redirect(url_for('auth.login'))
            
    return render_template('forgot_password.html')


@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """
    Password reset completion endpoint.
    
    Validates token and allows user to set new password.
    Implements one-time token usage.
    
    Args:
        token (str): Password reset token from email link
    """
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    # ============================================
    # CHECK IF TOKEN WAS ALREADY USED
    # ============================================
    
    if UsedPasswordResetToken.is_token_used(token):
        flash(
            'This password reset link has already been used. '
            'Please request a new one if needed.',
            'error'
        )
        return redirect(url_for('auth.forgot_password'))
    
    # ============================================
    # VERIFY TOKEN SIGNATURE AND EXPIRATION
    # ============================================
    
    try:
        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        # Token expires after 1 hour
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except SignatureExpired:
        flash('The reset link has expired. Please request a new one.', 'error')
        return redirect(url_for('auth.forgot_password'))
    except BadSignature:
        flash('Invalid reset link.', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    # ============================================
    # PROCESS PASSWORD RESET
    # ============================================
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        
        # Validate passwords match
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)
        
        # Find user
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('auth.login'))
        
        try:
            # Set new password (will validate complexity)
            user.set_password(password)
            db.session.commit()
            
            # Mark token as used
            UsedPasswordResetToken.mark_token_used(
                token, 
                email, 
                ip_address=get_client_ip()
            )
            
            # Log password change
            log_password_change(user.id, changed_by_admin=False)
            sec_log.log_security_event(
                user.id,
                sec_log.EVENT_PASSWORD_RESET_COMPLETE,
                details="Password reset via email link"
            )
            
            flash(
                'Your password has been updated successfully! You can now log in.',
                'success'
            )
            return redirect(url_for('auth.login'))
            
        except ValueError as e:
            # Password validation failed
            flash(str(e), 'error')
            return render_template('reset_password.html', token=token)
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Password reset error: {e}")
            flash('An error occurred. Please try again.', 'error')
            return render_template('reset_password.html', token=token)
    
    return render_template('reset_password.html', token=token)