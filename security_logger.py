"""
Security Event Logger for SchoolSync Pro
=========================================
Provides audit trail for security-related events.

Author: SchoolSync Team
Last Updated: 2026-01-16
"""

from flask import request
from datetime import datetime
import sys


# ============================================
# SECURITY EVENT TYPES
# ============================================

EVENT_LOGIN_SUCCESS = 'login_success'
EVENT_LOGIN_FAILED = 'login_failed'
EVENT_LOGOUT = 'logout'
EVENT_PASSWORD_CHANGE = 'password_change'
EVENT_PASSWORD_RESET_REQUEST = 'password_reset_request'
EVENT_PASSWORD_RESET_COMPLETE = 'password_reset_complete'
EVENT_2FA_ENABLED = '2fa_enabled'
EVENT_2FA_DISABLED = '2fa_disabled'
EVENT_PROFILE_UPDATE = 'profile_update'
EVENT_STUDENT_DELETE = 'student_delete'
EVENT_BULK_DELETE = 'bulk_delete'
EVENT_BULK_IMPORT = 'bulk_import'
EVENT_ACCOUNT_LOCKED = 'account_locked'


# ============================================
# LOGGING FUNCTIONS
# ============================================

def log_security_event(user_id, event_type, details=None, ip_address=None, user_agent=None):
    """
    Log a security-related event for audit trail.
    
    Args:
        user_id (int): ID of user performing the action (None for anonymous)
        event_type (str): Type of security event (use constants above)
        details (str): Optional additional details
        ip_address (str): IP address (auto-detected if None)
        user_agent (str): User agent string (auto-detected if None)
        
    Returns:
        bool: True if logged successfully, False otherwise
    """
    try:
        # Import here to avoid circular dependency
        from models import SecurityLog
        from extensions import db
        
        # Auto-detect IP and User-Agent if not provided
        if ip_address is None:
            ip_address = get_client_ip()
        
        if user_agent is None:
            user_agent = request.headers.get('User-Agent', 'Unknown')[:255]
        
        # Create log entry
        log = SecurityLog(
            user_id=user_id,
            event_type=event_type,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
            timestamp=datetime.utcnow()
        )
        
        db.session.add(log)
        db.session.commit()
        
        # Also log to console for debugging
        print(f"🔒 Security Event: {event_type} | User: {user_id or 'Anonymous'} | IP: {ip_address}", 
              file=sys.stdout)
        
        return True
        
    except Exception as e:
        # Don't break the application if logging fails
        print(f"❌ Security logging failed: {e}", file=sys.stderr)
        return False


def log_failed_login(username, reason='Invalid credentials'):
    """
    Log a failed login attempt.
    
    Args:
        username (str): Username that attempted login
        reason (str): Reason for failure
    """
    details = f"Username: {username} | Reason: {reason}"
    log_security_event(
        user_id=None,  # No user ID for failed login
        event_type=EVENT_LOGIN_FAILED,
        details=details
    )


def log_successful_login(user_id, username, method='password'):
    """
    Log a successful login.
    
    Args:
        user_id (int): ID of logged in user
        username (str): Username
        method (str): Authentication method (password, 2fa_email, 2fa_app)
    """
    details = f"Username: {username} | Method: {method}"
    log_security_event(
        user_id=user_id,
        event_type=EVENT_LOGIN_SUCCESS,
        details=details
    )


def log_logout(user_id, username):
    """
    Log a logout event.
    
    Args:
        user_id (int): ID of logged out user
        username (str): Username
    """
    log_security_event(
        user_id=user_id,
        event_type=EVENT_LOGOUT,
        details=f"Username: {username}"
    )


def log_password_change(user_id, changed_by_admin=False):
    """
    Log a password change.
    
    Args:
        user_id (int): ID of user whose password changed
        changed_by_admin (bool): True if changed by admin, False if self-change
    """
    details = "Changed by admin" if changed_by_admin else "Self-service change"
    log_security_event(
        user_id=user_id,
        event_type=EVENT_PASSWORD_CHANGE,
        details=details
    )


def log_2fa_change(user_id, enabled, method=None):
    """
    Log 2FA enable/disable event.
    
    Args:
        user_id (int): ID of user
        enabled (bool): True if enabled, False if disabled
        method (str): 2FA method (email, app, sms) if enabled
    """
    if enabled:
        details = f"Method: {method}"
        event_type = EVENT_2FA_ENABLED
    else:
        details = "2FA disabled"
        event_type = EVENT_2FA_DISABLED
    
    log_security_event(
        user_id=user_id,
        event_type=event_type,
        details=details
    )


def log_profile_update(user_id, fields_changed):
    """
    Log profile update.
    
    Args:
        user_id (int): ID of user
        fields_changed (list): List of field names that were changed
    """
    details = f"Fields updated: {', '.join(fields_changed)}"
    log_security_event(
        user_id=user_id,
        event_type=EVENT_PROFILE_UPDATE,
        details=details
    )


def log_student_delete(user_id, student_id, student_name):
    """
    Log student deletion.
    
    Args:
        user_id (int): ID of user performing deletion
        student_id (int): ID of deleted student
        student_name (str): Name of deleted student
    """
    details = f"Student ID: {student_id} | Name: {student_name}"
    log_security_event(
        user_id=user_id,
        event_type=EVENT_STUDENT_DELETE,
        details=details
    )


def log_bulk_operation(user_id, operation_type, count, success_count, error_count=0):
    """
    Log bulk operations (import, delete, etc.).
    
    Args:
        user_id (int): ID of user performing operation
        operation_type (str): Type of bulk operation
        count (int): Total records processed
        success_count (int): Number of successful operations
        error_count (int): Number of failed operations
    """
    details = f"Type: {operation_type} | Total: {count} | Success: {success_count} | Errors: {error_count}"
    log_security_event(
        user_id=user_id,
        event_type=EVENT_BULK_IMPORT if operation_type == 'import' else EVENT_BULK_DELETE,
        details=details
    )


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_client_ip():
    """
    Get client IP address, handling proxies.
    
    Returns:
        str: Client IP address
    """
    # Check for proxy headers
    if request.headers.get('X-Forwarded-For'):
        # X-Forwarded-For can contain multiple IPs, get the first one
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP')
    else:
        ip = request.remote_addr or 'Unknown'
    
    # Limit length to prevent database issues
    return ip[:45]


def get_recent_failed_logins(username=None, ip_address=None, hours=24):
    """
    Get recent failed login attempts for account lockout detection.
    
    Args:
        username (str): Filter by username
        ip_address (str): Filter by IP address
        hours (int): Look back this many hours
        
    Returns:
        list: List of SecurityLog entries
    """
    try:
        from models import SecurityLog
        from datetime import timedelta
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        query = SecurityLog.query.filter(
            SecurityLog.event_type == EVENT_LOGIN_FAILED,
            SecurityLog.timestamp >= cutoff
        )
        
        if username:
            query = query.filter(SecurityLog.details.contains(f"Username: {username}"))
        
        if ip_address:
            query = query.filter(SecurityLog.ip_address == ip_address)
        
        return query.order_by(SecurityLog.timestamp.desc()).all()
        
    except Exception as e:
        print(f"❌ Failed to retrieve login history: {e}", file=sys.stderr)
        return []
