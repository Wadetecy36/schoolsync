from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
from datetime import datetime, timedelta
from utils import generate_otp, send_email_otp, send_sms_otp
import re

auth = Blueprint('auth', __name__)

@auth.before_request
def make_session_permanent():
    """Make session permanent with timeout"""
    session.permanent = True

@auth.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    # Check for failed login attempts (Rate Limiting)
    failed_attempts = session.get('failed_attempts', 0)
    last_attempt = session.get('last_attempt')
    
    if last_attempt:
        last_attempt_time = datetime.fromisoformat(last_attempt)
        if failed_attempts >= 5 and datetime.now() - last_attempt_time < timedelta(minutes=15):
            if request.is_json:
                return jsonify({'success': False, 'error': 'Too many failed attempts. Try again in 15 minutes.'}), 429
            flash('Too many failed attempts. Try again in 15 minutes.', 'error')
            return render_template('login.html')
    
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        password = data.get('password', '')
        # Handle 'remember' checkbox which returns 'on' in forms, or boolean in JSON
        remember = data.get('remember')
        if remember == 'on': remember = True
        
        # Validate input
        if not username or not password:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Username and password required'}), 400
            flash('Username and password required', 'error')
            return redirect(url_for('auth.login'))
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            # Check if account is disabled
            if not user.is_active:
                session['failed_attempts'] = failed_attempts + 1
                session['last_attempt'] = datetime.now().isoformat()
                
                if request.is_json:
                    return jsonify({'success': False, 'error': 'Account is disabled'}), 403
                flash('Your account has been disabled. Contact administrator.', 'error')
                return redirect(url_for('auth.login'))
            
            # --- 2FA LOGIC STARTS HERE ---
            if user.two_factor_method in ['email', 'sms']:
                # Generate OTP
                otp = generate_otp()
                user.otp_code = otp
                user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
                db.session.commit()
                
                # Send OTP
                sent = False
                flash_msg = ""
                
                if user.two_factor_method == 'sms' and user.phone:
                    sent = send_sms_otp(user.phone, otp)
                    flash_msg = f'Verification code sent to phone ending in {user.phone[-4:]}'
                else:
                    # Default to email
                    sent = send_email_otp(user.email, otp)
                    flash_msg = f'Verification code sent to {user.email}'
                
                if sent:
                    # Store temp session data (User is NOT logged in yet)
                    session['2fa_user_id'] = user.id
                    session['remember_me'] = remember
                    
                    # Reset failed attempts since password was correct
                    session.pop('failed_attempts', None)
                    session.pop('last_attempt', None)
                    
                    if request.is_json:
                        return jsonify({'success': True, 'message': '2FA required', 'redirect': url_for('auth.verify_2fa')})
                    
                    flash(flash_msg, 'info')
                    return redirect(url_for('auth.verify_2fa'))
                else:
                    if request.is_json:
                        return jsonify({'success': False, 'error': 'Failed to send verification code'}), 500
                    flash('Error sending verification code. Please contact admin.', 'error')
                    return redirect(url_for('auth.login'))
            # --- 2FA LOGIC ENDS ---

            # Standard Login (No 2FA)
            session.pop('failed_attempts', None)
            session.pop('last_attempt', None)
            
            # Update last login
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            login_user(user, remember=remember)
            
            if request.is_json:
                return jsonify({'success': True, 'message': 'Login successful'})
            
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('main.index'))
        else:
            # Increment failed attempts
            session['failed_attempts'] = failed_attempts + 1
            session['last_attempt'] = datetime.now().isoformat()
            
            if request.is_json:
                return jsonify({'success': False, 'error': 'Invalid username or password'}), 401
            
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@auth.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa():
    """2FA Verification Page"""
    user_id = session.get('2fa_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        code = request.form.get('otp_code', '').strip()
        
        # Validation checks
        if not user.otp_code or not user.otp_expiry:
            flash('Session invalid. Please login again.', 'error')
            return redirect(url_for('auth.login'))
            
        if datetime.utcnow() > user.otp_expiry:
            flash('Code expired. Please login again.', 'warning')
            return redirect(url_for('auth.login'))
            
        if code == user.otp_code:
            # Code Correct - Log them in
            user.otp_code = None
            user.otp_expiry = None
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            remember = session.get('remember_me', False)
            
            # Clear temp session
            session.pop('2fa_user_id', None)
            session.pop('remember_me', None)
            
            login_user(user, remember=remember)
            
            flash('Verification successful', 'success')
            return redirect(url_for('main.index'))
        else:
            flash('Invalid code. Please try again.', 'error')
            
    return render_template('verify_2fa.html', method=user.two_factor_method)

@auth.route('/register', methods=['GET', 'POST'])
def register():
    """Register new admin"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        full_name = data.get('full_name', '').strip()
        
        # Validate inputs
        errors = []
        
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters')
        
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            errors.append('Username can only contain letters, numbers, and underscores')
        
        if not email or '@' not in email:
            errors.append('Valid email is required')
        
        if not User.validate_password(password):
            errors.append('Password must be at least 8 characters with uppercase, lowercase, number, and special character')
        
        if password != confirm_password:
            errors.append('Passwords do not match')
        
        if not full_name or len(full_name) < 2:
            errors.append('Full name is required')
        
        # Check for existing user
        if User.query.filter_by(username=username).first():
            errors.append('Username already exists')
        
        if User.query.filter_by(email=email).first():
            errors.append('Email already exists')
        
        if errors:
            if request.is_json:
                return jsonify({'success': False, 'error': '; '.join(errors)}), 400
            for error in errors:
                flash(error, 'error')
            return redirect(url_for('auth.register'))
        
        # Create user
        try:
            user = User(
                username=username,
                email=email,
                full_name=full_name,
                role='admin'
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            if request.is_json:
                return jsonify({'success': True, 'message': 'Registration successful'})
            
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('auth.login'))
            
        except ValueError as e:
            if request.is_json:
                return jsonify({'success': False, 'error': str(e)}), 400
            flash(str(e), 'error')
            return redirect(url_for('auth.register'))
        except Exception as e:
            db.session.rollback()
            if request.is_json:
                return jsonify({'success': False, 'error': 'Registration failed'}), 500
            flash('Registration failed. Please try again.', 'error')
            return redirect(url_for('auth.register'))
    
    return render_template('register.html')

@auth.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('auth.login'))

@auth.route('/api/auth/check')
def check_auth():
    """Check if user is authenticated"""
    return jsonify({
        'authenticated': current_user.is_authenticated,
        'user': {
            'username': current_user.username,
            'full_name': current_user.full_name,
            'role': current_user.role,
            'is_super_admin': current_user.is_super_admin if current_user.is_authenticated else False
        } if current_user.is_authenticated else None
    })

@auth.route('/api/auth/change-password', methods=['POST'])
@login_required
def change_password():
    """Change user password"""
    try:
        data = request.get_json()
        
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        # Validate
        if not current_password or not new_password or not confirm_password:
            return jsonify({'success': False, 'error': 'All fields are required'}), 400
        
        if not current_user.check_password(current_password):
            return jsonify({'success': False, 'error': 'Current password is incorrect'}), 401
        
        if new_password != confirm_password:
            return jsonify({'success': False, 'error': 'New passwords do not match'}), 400
        
        if not User.validate_password(new_password):
            return jsonify({'success': False, 'error': 'Password must be at least 8 characters with uppercase, lowercase, number, and special character'}), 400
        
        # Update password
        current_user.set_password(new_password)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Password changed successfully'})
        
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# Helper route to enable 2FA for testing
@auth.route('/enable-test-2fa/<method>')
@login_required
def enable_test_2fa(method):
    if method not in ['email', 'sms', 'off']:
        return "Invalid method", 400
        
    if method == 'off':
        current_user.two_factor_method = None
    else:
        current_user.two_factor_method = method
        # Set a dummy phone for testing if none exists
        if method == 'sms' and not current_user.phone:
            current_user.phone = "+1234567890" 
            
    db.session.commit()
    return f"2FA set to {method}. <a href='/logout'>Logout to test</a>"