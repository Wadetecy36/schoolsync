"""
Database Models for SchoolSync Pro
===================================
Defines all database models including User, Student, AcademicRecord,
SecurityLog, and UsedPasswordResetToken.

Author: SchoolSync Team
Last Updated: 2026-01-16
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import re
import hashlib

from extensions import db
from datetime import datetime

# ============================================
# VALIDATION CONSTANTS
# ============================================

VALID_HALLS = [
    "Alema Hall", "Ellen Hall", "Halm Addo Hall", "Nana Wereko Ampem II Hall",
    "Wilson Q .Tei Hall", "Awuletey Hall", "Peter Ala Adjetey Hall",
    "Nana Akuako Sarpong Hall", "Nana Awuah Darko Ampem Hall"
]

VALID_PROGRAMS = [
    "General Science", "Business", "General Arts", 
    "Visual Arts", "Agriculture", "Home Economics"
]


# ============================================
# USER MODEL
# ============================================

class User(UserMixin, db.Model):
    """
    User model for authentication and authorization.
    
    Supports role-based access control (admin, super_admin) and
    multi-factor authentication (Email OTP, SMS OTP, TOTP).
    """
    __tablename__ = 'users'
    
    # Basic Information
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100))
    
    # Authorization
    role = db.Column(db.String(20), default='admin')  # admin, super_admin
    is_active = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Two-Factor Authentication (2FA)
    phone = db.Column(db.String(20))
    two_factor_method = db.Column(db.String(10), default=None)  # email, sms, app, None
    otp_code = db.Column(db.String(6))  # For email/SMS OTP
    otp_expiry = db.Column(db.DateTime)  # OTP expiration time
    totp_secret = db.Column(db.String(32))  # For TOTP (Google Authenticator)
    
    # Relationships
    created_students = db.relationship(
        'Student', 
        backref='creator', 
        lazy='dynamic', 
        foreign_keys='Student.created_by'
    )
    
    security_logs = db.relationship(
        'SecurityLog',
        backref='user',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    def set_password(self, password):
        """
        Hash and set user password.
        
        Args:
            password (str): Plain text password
            
        Raises:
            ValueError: If password doesn't meet complexity requirements
        """
        if not self.validate_password(password):
            raise ValueError(
                "Password must be 8+ characters with uppercase, lowercase, "
                "number, and special character."
            )
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """
        Verify password against stored hash.
        
        Args:
            password (str): Plain text password to verify
            
        Returns:
            bool: True if password matches, False otherwise
        """
        return check_password_hash(self.password_hash, password)
    
    @staticmethod
    def validate_password(password):
        """
        Validate password complexity.
        
        Requirements:
        - At least 8 characters
        - Contains uppercase letter
        - Contains lowercase letter
        - Contains digit
        - Contains special character
        
        Args:
            password (str): Password to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if len(password) < 8:
            return False
        if not re.search(r"[A-Z]", password):
            return False
        if not re.search(r"[a-z]", password):
            return False
        if not re.search(r"\d", password):
            return False
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            return False
        return True
    
    @property
    def is_super_admin(self):
        """Check if user has super admin privileges."""
        return self.role == 'super_admin'

    def __repr__(self):
        return f'<User {self.username}>'

class Blacklist(db.Model):
    """Model for tracking blacklisted students"""
    __tablename__ = 'blacklist'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False, unique=True)
    reason = db.Column(db.Text, nullable=False)
    added_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date_added = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Relationships
    student = db.relationship('Student', backref=db.backref('blacklist_entry', uselist=False, lazy=True))
    added_by_user = db.relationship('User', backref='blacklisted_students')
    
    def __repr__(self):
        return f'<Blacklist {self.student.name if self.student else "Unknown"}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.name if self.student else None,
            'reason': self.reason,
            'added_by': self.added_by_user.username if self.added_by_user else None,
            'date_added': self.date_added.strftime('%Y-%m-%d %H:%M:%S'),
            'is_active': self.is_active
        }


# ============================================
# STUDENT MODEL
# ============================================

class Student(db.Model):
    """
    Student model for managing student records.
    
    Includes personal information, academic details, guardian information,
    and optional photo (stored as Base64).
    """
    __tablename__ = 'students'
    
    # Basic Information
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    gender = db.Column(db.String(20))
    # Using String for date_of_birth to be lenient with SQLite's dynamic typing
    date_of_birth = db.Column(db.String(20))
    
    # Academic Information
    program = db.Column(db.String(100), index=True)
    hall = db.Column(db.String(100))
    class_room = db.Column(db.String(20))
    enrollment_year = db.Column(db.Integer, nullable=False, index=True)
    
    # Contact Information
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    
    # Guardian Information
    guardian_name = db.Column(db.String(100))
    guardian_phone = db.Column(db.String(20))
    
    # Photo (Base64 encoded)
    photo_file = db.Column(db.Text)
    face_encoding = db.Column(db.Text)  # JSON encoded list of 128-dimensional face encoding vectors
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Relationships
    academic_history = db.relationship(
        'AcademicRecord', 
        backref='student', 
        lazy='dynamic', 
        cascade='all, delete-orphan'
    )
    
    # Composite Indexes for Performance
    __table_args__ = (
        db.Index('ix_students_created_by', 'created_by'),
        db.Index('ix_students_program_year', 'program', 'enrollment_year'),  # NEW: Dashboard filter optimization
        db.Index('ix_students_hall_year', 'hall', 'enrollment_year'),  # NEW: Dashboard filter optimization
    )
    
    @property
    def current_form(self):
        """
        Calculate current form/grade based on enrollment year.
        
        Returns:
            str: 'First Form', 'Second Form', 'Third Form', or 'Completed'
        """
        current_year = datetime.now().year
        diff = current_year - self.enrollment_year
        
        if diff >= 3:
            return "Completed"
        elif diff == 2:
            return "Third Form"
        elif diff == 1:
            return "Second Form"
        else:
            return "First Form"
    
    @property
    def age(self):
        """
        Calculate current age from date of birth.
        Safe against non-date types in database.
        
        Returns:
            int: Age in years, or None if DOB not set or invalid
        """
        try:
            dob = self.date_of_birth
            if dob:
                # Handle string format if SQLite returned it as such
                if isinstance(dob, str):
                    from datetime import date
                    dob = date.fromisoformat(dob.split(' ')[0])

                if hasattr(dob, 'year'):
                    today = datetime.now().date()
                    return today.year - dob.year - (
                        (today.month, today.day) < (dob.month, dob.day)
                    )
        except (ValueError, TypeError, AttributeError):
            pass
        return None
    
    def to_dict(self):
        """
        Convert student model to dictionary for JSON serialization.
        Includes extensive error handling for data consistency.
        
        Returns:
            dict: Student data with calculated fields
        """
        # 1. Safe Date Handling
        dob_iso = None
        current_age = None

        try:
            dob = self.date_of_birth
            if dob:
                # Normalization if it's a string
                if isinstance(dob, str):
                    from datetime import date
                    # SQLite sometimes stores "YYYY-MM-DD HH:MM:SS" even for Date columns
                    dob = date.fromisoformat(dob.split(' ')[0])

                if hasattr(dob, 'year'):
                    dob_iso = dob.isoformat()
                    today = datetime.now().date()
                    current_age = today.year - dob.year - (
                        (today.month, today.day) < (dob.month, dob.day)
                    )
                else:
                    dob_iso = str(dob)
        except (ValueError, TypeError, AttributeError):
            # Attempt to get raw value if attribute access failed
            try:
                dob_iso = str(self.__dict__.get('date_of_birth'))
            except:
                dob_iso = None

        # 2. Photo URL logic (Safe)
        photo_url = None
        try:
            if self.photo_file:
                if self.photo_file.startswith('http') or self.photo_file.startswith('data:'):
                    photo_url = self.photo_file
                else:
                    photo_url = f"/static/uploads/{self.photo_file}"
        except Exception:
            photo_url = None

        # 3. Blacklist Status (Safe)
        is_blacklisted = False
        try:
            if self.blacklist_entry:
                is_blacklisted = getattr(self.blacklist_entry, 'is_active', False)
        except Exception:
            pass

        # 4. Form Calculation (Safe)
        curr_form = "Unknown"
        try:
            curr_form = self.current_form
        except Exception:
            pass

        return {
            'id': self.id,
            'name': self.name,
            'gender': self.gender,
            'date_of_birth': dob_iso,
            'age': current_age,
            'program': self.program,
            'hall': self.hall,
            'class_room': self.class_room,
            'enrollment_year': self.enrollment_year,
            'current_form': curr_form,
            'photo_url': photo_url,
            'email': self.email,
            'phone': self.phone,
            'guardian_name': self.guardian_name,
            'guardian_phone': self.guardian_phone,
            'created_by': self.created_by,
            'is_blacklisted': is_blacklisted
        }

    def has_permission(self, user):
        """
        Check if user has permission to modify this student record.
        
        Args:
            user (User): User to check permissions for
            
        Returns:
            bool: True if user can modify, False otherwise
        """
        # Allow super_admins OR any user with 'admin' role to manage students
        # This prevents "orphan" students if an admin leaves
        return user.is_super_admin or user.role == 'admin'

    def __repr__(self):
        return f'<Student {self.name}>'


# ============================================
# ACADEMIC RECORD MODEL
# ============================================

class AcademicRecord(db.Model):
    """
    Academic records for student performance tracking.
    
    Stores academic performance data by form and year.
    """
    __tablename__ = 'academic_records'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, 
        db.ForeignKey('students.id', ondelete='CASCADE'), 
        nullable=False
    )
    form = db.Column(db.String(50), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    gpa = db.Column(db.Float)
    remarks = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Indexes for performance
    __table_args__ = (
        db.Index('ix_academic_records_student_id', 'student_id'),
        db.Index('ix_academic_records_year', 'year'),
    )

    def __repr__(self):
        return f'<AcademicRecord Student:{self.student_id} Year:{self.year}>'


# ============================================
# SECURITY LOG MODEL
# ============================================

class SecurityLog(db.Model):
    """
    Audit trail for security-related events.
    
    Tracks login attempts, password changes, profile updates,
    and other security-sensitive operations.
    """
    __tablename__ = 'security_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # NULL for anonymous events
    event_type = db.Column(db.String(50), nullable=False, index=True)
    ip_address = db.Column(db.String(45))  # IPv6 compatible
    user_agent = db.Column(db.String(255))
    details = db.Column(db.Text)  # Additional event details (JSON or text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Indexes for query performance
    __table_args__ = (
        db.Index('ix_security_logs_user_event', 'user_id', 'event_type'),
        db.Index('ix_security_logs_timestamp_event', 'timestamp', 'event_type'),
    )

    def __repr__(self):
        return f'<SecurityLog {self.event_type} at {self.timestamp}>'


# ============================================
# PASSWORD RESET TOKEN MODEL
# ============================================

class UsedPasswordResetToken(db.Model):
    """
    Tracks used password reset tokens to prevent reuse.
    
    Password reset tokens can only be used once for security.
    Old tokens are cleaned up periodically.
    """
    __tablename__ = 'used_password_reset_tokens'
    
    token_hash = db.Column(db.String(64), primary_key=True)  # SHA256 hash of token
    email = db.Column(db.String(120), nullable=False, index=True)
    used_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    ip_address = db.Column(db.String(45))
    
    @staticmethod
    def hash_token(token):
        """
        Create SHA256 hash of token for secure storage.
        
        Args:
            token (str): Raw token string
            
        Returns:
            str: Hexadecimal hash string
        """
        return hashlib.sha256(token.encode()).hexdigest()
    
    @classmethod
    def is_token_used(cls, token):
        """
        Check if a token has already been used.
        
        Args:
            token (str): Token to check
            
        Returns:
            bool: True if token was used, False otherwise
        """
        token_hash = cls.hash_token(token)
        return cls.query.filter_by(token_hash=token_hash).first() is not None
    
    @classmethod
    def mark_token_used(cls, token, email, ip_address=None):
        """
        Mark a token as used.
        
        Args:
            token (str): Token that was used
            email (str): Email address associated with token
            ip_address (str): IP address of user (optional)
        """
        token_hash = cls.hash_token(token)
        used_token = cls(
            token_hash=token_hash,
            email=email,
            ip_address=ip_address
        )
        db.session.add(used_token)
        db.session.commit()

    def __repr__(self):
        return f'<UsedPasswordResetToken {self.email} at {self.used_at}>'
