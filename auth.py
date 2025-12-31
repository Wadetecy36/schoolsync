from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
from datetime import datetime, timedelta
from utils import generate_otp, send_email_otp, send_sms_otp
import re

auth = Blueprint('auth', __name__)

@auth.before_request
def make_session_permanent():
    session.permanent = True

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        password = data.get('password', '')
        remember = data.get('remember') == 'on' or data.get('remember') == True
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            # 2FA Logic
            if user.two_factor_method in ['email', 'sms']:
                otp = generate_otp()
                user.otp_code = otp
                user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
                db.session.commit()
                
                if user.two_factor_method == 'sms' and user.phone:
                    send_sms_otp(user.phone, otp)
                    flash_msg = f'Code sent to phone ending in {user.phone[-4:]}'
                else:
                    send_email_otp(user.email, otp)
                    flash_msg = f'Code sent to {user.email}'
                
                session['2fa_user_id'] = user.id
                session['remember_me'] = remember
                
                if request.is_json:
                    return jsonify({'success': True, 'redirect': url_for('auth.verify_2fa')})
                flash(flash_msg, 'info')
                return redirect(url_for('auth.verify_2fa'))

            # Normal Login
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user, remember=remember)
            
            if request.is_json:
                return jsonify({'success': True})
            return redirect(url_for('main.index'))
            
        flash('Invalid username or password', 'error')
        if request.is_json:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

    return render_template('login.html')

@auth.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa():
    user_id = session.get('2fa_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        code = request.form.get('otp_code', '').strip()
        
        if not user.otp_code or not user.otp_expiry or datetime.utcnow() > user.otp_expiry:
            flash('Code expired or invalid session.', 'error')
            return redirect(url_for('auth.login'))
            
        if code == user.otp_code:
            try:
                # Login Success
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
                flash('System error during login.', 'error')
                return redirect(url_for('auth.login'))
        else:
            flash('Invalid code.', 'error')
            
    return render_template('verify_2fa.html', method=user.two_factor_method)

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('auth.login'))

@auth.route('/api/auth/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json()
    current = data.get('current_password')
    new_pass = data.get('new_password')
    
    if not current_user.check_password(current):
        return jsonify({'success': False, 'error': 'Current password incorrect'}), 400
        
    try:
        current_user.set_password(new_pass)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Password updated'})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400