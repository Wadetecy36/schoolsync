from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import re

db = SQLAlchemy()


# --- CONSTANTS FOR VALIDATION ---
VALID_HALLS = [
    "Alema Hall", "Ellen Hall", "Halm Addo Hall", "Nana Wereko Ampem II Hall",
    "Wilson Q .Tei Hall", "Awuletey Hall", "Peter Ala Adjetey Hall",
    "Nana Akuako Sarpong Hall", "Nana Awuah Darko Ampem Hall"
]

VALID_PROGRAMS = [
    "General Science", "Business", "General Arts", 
    "Visual Arts", "Agriculture", "Home Economics"
]


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100))
    role = db.Column(db.String(20), default='admin')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # New 2FA Columns
    phone = db.Column(db.String(20))
    two_factor_method = db.Column(db.String(10), default=None) 
    otp_code = db.Column(db.String(6))
    otp_expiry = db.Column(db.DateTime)
    totp_secret = db.Column(db.String(32)) 
    # Relationship
    created_students = db.relationship('Student', backref='creator', lazy='dynamic', foreign_keys='Student.created_by')
    
    def set_password(self, password):
        if not self.validate_password(password):
            raise ValueError("Password must be at least 8 characters with uppercase, lowercase, number, and special character")
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @staticmethod
    def validate_password(password):
        if len(password) < 8: return False
        if not re.search(r"[A-Z]", password): return False
        if not re.search(r"[a-z]", password): return False
        if not re.search(r"\d", password): return False
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password): return False
        return True
    
    @property
    def is_super_admin(self):
        return self.role == 'super_admin'
    
    def __repr__(self):
        return f'<User {self.username}>'

class Student(db.Model):
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)
    # FIX: Removed index=True from columns because they are in __table_args__
    name = db.Column(db.String(100), nullable=False) 
    gender = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    program = db.Column(db.String(100))
    hall = db.Column(db.String(100))
    class_room = db.Column(db.String(20))
    enrollment_year = db.Column(db.Integer, nullable=False)
    photo = db.Column(db.String(200), default='default.jpg')
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    guardian_name = db.Column(db.String(100))
    guardian_phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Relationships
    academic_history = db.relationship('AcademicRecord', backref='student', lazy='dynamic', cascade='all, delete-orphan')
    
    __table_args__ = (
        db.Index('ix_students_name', 'name'),
        db.Index('ix_students_program', 'program'),
        db.Index('ix_students_enrollment_year', 'enrollment_year'),
        db.Index('ix_students_created_by', 'created_by'),
    )
    
    @property
    def current_form(self):
        current_year = datetime.now().year
        diff = current_year - self.enrollment_year
        if diff >= 3: return "Completed"
        elif diff == 2: return "Third Form"
        elif diff == 1: return "Second Form"
        else: return "First Form"
    
    @property
    def age(self):
        if self.date_of_birth:
            today = datetime.now().date()
            return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        return None
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'gender': self.gender,
            'date_of_birth': self.date_of_birth.isoformat() if self.date_of_birth else None,
            'program': self.program,
            'hall': self.hall,
            'class_room': self.class_room,
            'enrollment_year': self.enrollment_year,
            'current_form': self.current_form,
            'photo': self.photo,
            'email': self.email,
            'phone': self.phone,
            'age': self.age,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by': self.created_by
        }
    
    def has_permission(self, user):
        return user.is_super_admin or self.created_by == user.id
    
    def __repr__(self):
        return f'<Student {self.name}>'

class AcademicRecord(db.Model):
    __tablename__ = 'academic_records'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    form = db.Column(db.String(50), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    gpa = db.Column(db.Float)
    remarks = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.Index('ix_academic_records_student_id', 'student_id'),
        db.Index('ix_academic_records_year', 'year'),
    )
    
    def __repr__(self):
        return f'<AcademicRecord {self.form} - {self.year}>'