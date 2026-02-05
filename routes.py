"""
Main Routes Module for SchoolSync Pro
======================================
Handles student management, data import/export, settings, and dashboard.

Author: SchoolSync Team
Last Updated: 2026-01-16
"""

from flask import (
    Blueprint, render_template, request, jsonify, send_file, 
    redirect, url_for, flash, current_app
)
from extensions import db
from models import Student, AcademicRecord, User, Blacklist, VALID_HALLS, VALID_PROGRAMS
from datetime import datetime
from sqlalchemy import or_, and_, func
from flask_login import login_required, current_user
from functools import wraps
import pandas as pd
import io
import os
from werkzeug.utils import secure_filename
import pyotp 
import re

# Import utilities
from utils import generate_qr_code, get_totp_uri
from PIL import Image
import base64
import json
from face_handler import FaceHandler

# Import validators
from validators import (
    validate_email, validate_phone, validate_date_of_birth,
    validate_image_file, validate_data_file, sanitize_search_query,
    validate_text_length, MAX_IMAGE_SIZE
)

# Import security logging
from security_logger import (
    log_profile_update, log_2fa_change, log_student_delete,
    log_bulk_operation
)

# Create Blueprint
main = Blueprint('main', __name__)


# ============================================
# STATISTICS API ENDPOINT
# ============================================

@main.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    """
    Get dashboard statistics.
    
    Returns student counts by form level using optimized SQL aggregation.
    
    Returns:
        JSON: {
            success: bool,
            stats: {
                total_students: int,
                new_this_month: int,
                by_form: dict,
                by_program: dict
            }
        }
    """
    try:
        total = Student.query.count()
        current_year = datetime.now().year

        # Calculate new students this month
        first_day_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        new_this_month = Student.query.filter(Student.created_at >= first_day_of_month).count()

        # Calculate form distribution
        form_counts = {
            'First Form': 0,
            'Second Form': 0,
            'Third Form': 0,
            'Completed': 0
        }

        # Optimized SQL aggregation for forms (by enrollment year)
        form_rows = db.session.query(
            Student.enrollment_year,
            func.count(Student.id)
        ).group_by(Student.enrollment_year).all()

        for year, count in form_rows:
            if year is None:
                form_counts['First Form'] += count
                continue
            try:
                diff = current_year - int(year)
                if diff >= 3:
                    form_counts['Completed'] += count
                elif diff == 2:
                    form_counts['Third Form'] += count
                elif diff == 1:
                    form_counts['Second Form'] += count
                else:
                    form_counts['First Form'] += count
            except (ValueError, TypeError):
                form_counts['First Form'] += count

        # Calculate program distribution
        program_rows = db.session.query(
            Student.program,
            func.count(Student.id)
        ).group_by(Student.program).all()
        by_program = { (row[0] or 'Unassigned'): row[1] for row in program_rows }

        return jsonify({
            'success': True,
            'stats': {
                'total': total,
                'total_students': total,
                'new_this_month': new_this_month,
                'newThisMonth': new_this_month,
                'avgAge': 16, # Placeholder if not explicitly needed
                'by_form': form_counts,
                'by_program': by_program
            }
        })
    except Exception as e:
        import traceback
        current_app.logger.error(f"Error in get_stats: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Failed to fetch statistics: {str(e)}'
        }), 500

@main.route('/api/students/stats/dashboard', methods=['GET'])
@login_required
def get_dashboard_stats_standard():
    """Standardized endpoint for Node.js dashboard"""
    return get_stats()


# ============================================
# HELPER FUNCTIONS
# ============================================

def allowed_file(filename):
    """
    Check if file extension is allowed for images.
    
    Args:
        filename (str): Filename to check
        
    Returns:
        bool: True if allowed, False otherwise
    """
    return ('.' in filename and 
            filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'})


def process_image(file):
    """
    Resize and convert image to Bas64 string.
    
    - Validates image file
    - Converts to RGB (handles RGBA/PNG)
    - Resizes to max 400x400 (maintains aspect ratio)
    - Compresses as JPEG at 70% quality
    - Returns Base64 data URI
    
    Args:
        file: FileStorage object from Flask request
        
    Returns:
        str: Base64 data URI (data:image/jpeg;base64,...)
        
    Raises:
        Exception: If image processing fails
    """
    try:
        if not file:
            return None
        
        # Validate image file first
        is_valid, error_msg = validate_image_file(file)
        if not is_valid:
            raise Exception(error_msg)
        
        # Open image using Pillow
        img = Image.open(file)
        
        # Convert to RGB (in case of PNG with transparency or palette mode)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        
        # Resize: maintain aspect ratio, max 400x400px
        img.thumbnail((400, 400), Image.Resampling.LANCZOS)
        
        # Save to buffer as JPEG with compression
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=70, optimize=True)
        buf.seek(0)
        
        # Encode to Base64
        b64_str = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        # Return as data URI
        return f"data:image/jpeg;base64,{b64_str}"
        
    except Exception as e:
        raise Exception(f"Image processing failed: {str(e)}")


# ============================================
# VIEW ROUTES
# ============================================

@main.route('/')
@login_required
def index():
    """Dashboard/Home page."""
    return render_template('index.html')


@main.route('/students')
@login_required
def students():
    """Student management page."""
    return render_template('students.html')


@main.route('/import')
@login_required
def import_page():
    """Bulk import page."""
    return render_template('import.html')


@main.route('/settings', methods=['GET'])
@login_required
def settings():
    """
    User settings page.
    
    Generates QR code for 2FA setup if not already configured.
    """
    qr_code = None
    secret = None
    
    # Check if user already has TOTP secret
    current_secret = getattr(current_user, 'totp_secret', None)
    
    if not current_secret:
        # Generate new secret and QR code for 2FA setup
        temp_secret = pyotp.random_base32()
        current_user.totp_secret = temp_secret
        db.session.commit()
        
        uri, _ = get_totp_uri(current_user)
        qr_code = generate_qr_code(uri)
        secret = temp_secret
    
    return render_template('settings.html', qr_code=qr_code, new_secret=secret)


@main.route('/blacklist')
@login_required
def blacklist_page():
    """Display blacklist management page"""
    blacklisted = Blacklist.query.filter_by(is_active=True).order_by(Blacklist.date_added.desc()).all()
    return render_template('blacklist.html', blacklisted=blacklisted)

@main.route('/api/blacklist/add', methods=['POST'])
@login_required
def add_to_blacklist():
    """Add a student to the blacklist"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        reason = data.get('reason', '').strip()
        
        if not student_id:
            return jsonify({'success': False, 'message': 'Student ID is required'}), 400
        
        if not reason:
            return jsonify({'success': False, 'message': 'Reason is required'}), 400
        
        # Check if student exists
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Student not found'}), 404
        
        # Check if already blacklisted (active or inactive)
        existing = Blacklist.query.filter_by(student_id=student_id).first()
        
        if existing:
            if existing.is_active:
                return jsonify({'success': False, 'message': 'Student is already blacklisted'}), 400
            else:
                # Re-activate existing entry
                existing.is_active = True
                existing.reason = reason
                existing.added_by = current_user.id
                existing.date_added = datetime.utcnow()
                db.session.commit()
                
                return jsonify({
                    'success': True, 
                    'message': f'{student.name} has been added to the blacklist (re-activated)',
                    'data': existing.to_dict()
                }), 200
        
        # Add to blacklist
        blacklist_entry = Blacklist(
            student_id=student_id,
            reason=reason,
            added_by=current_user.id,
            date_added=datetime.utcnow()
        )
        
        db.session.add(blacklist_entry)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'{student.name} has been added to the blacklist',
            'data': blacklist_entry.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@main.route('/api/students/bulk-blacklist', methods=['POST'])
@login_required
def bulk_blacklist():
    """Add multiple students to the blacklist"""
    try:
        data = request.get_json()
        student_ids = data.get('ids', [])
        reason = data.get('reason', 'Bulk blacklisted').strip()
        
        if not student_ids:
            return jsonify({'success': False, 'message': 'No students selected'}), 400
            
        count = 0
        for sid in student_ids:
            # Check if student exists
            student = Student.query.get(sid)
            if not student:
                continue
                
            # Check if already blacklisted (active or inactive)
            existing = Blacklist.query.filter_by(student_id=sid).first()
            
            if existing:
                if not existing.is_active:
                    # Re-activate
                    existing.is_active = True
                    existing.reason = reason
                    existing.added_by = current_user.id
                    existing.date_added = datetime.utcnow()
                    count += 1
                # If active, skip
                continue
                
            # Add to blacklist
            blacklist_entry = Blacklist(
                student_id=sid,
                reason=reason,
                added_by=current_user.id,
                date_added=datetime.utcnow()
            )
            db.session.add(blacklist_entry)
            count += 1
            
        db.session.commit()
        return jsonify({
            'success': True, 
            'message': f'{count} students have been blacklisted'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@main.route('/api/blacklist/remove/<int:blacklist_id>', methods=['DELETE'])
@login_required
def remove_from_blacklist(blacklist_id):
    """Remove a student from the blacklist"""
    try:
        blacklist_entry = Blacklist.query.get(blacklist_id)
        
        if not blacklist_entry:
            return jsonify({'success': False, 'message': 'Blacklist entry not found'}), 404
        
        student_name = blacklist_entry.student.name if blacklist_entry.student else 'Student'
        
        # Soft delete - mark as inactive
        blacklist_entry.is_active = False
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'{student_name} has been removed from the blacklist'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@main.route('/api/blacklist/update/<int:blacklist_id>', methods=['PUT'])
@login_required
def update_blacklist_reason(blacklist_id):
    """Update the reason for a blacklist entry"""
    try:
        data = request.get_json()
        new_reason = data.get('reason', '').strip()
        
        if not new_reason:
            return jsonify({'success': False, 'message': 'Reason is required'}), 400
        
        blacklist_entry = Blacklist.query.get(blacklist_id)
        
        if not blacklist_entry:
            return jsonify({'success': False, 'message': 'Blacklist entry not found'}), 404
        
        blacklist_entry.reason = new_reason
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Blacklist reason updated successfully',
            'data': blacklist_entry.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@main.route('/api/blacklist/check/<int:student_id>')
@login_required
def check_blacklist_status(student_id):
    """Check if a student is blacklisted"""
    try:
        blacklist_entry = Blacklist.query.filter_by(student_id=student_id, is_active=True).first()

        return jsonify({
            'is_blacklisted': blacklist_entry is not None,
            'data': blacklist_entry.to_dict() if blacklist_entry else None
        }), 200
    except Exception as e:
        import traceback
        current_app.logger.error(f"Error in check_blacklist_status: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Check failed: {str(e)}'
        }), 500

@main.route('/api/students/search')
@login_required
def search_students():
    """Search students by name for autocomplete"""
    try:
        query = request.args.get('q', '').strip()

        if len(query) < 2:
            return jsonify([]), 200

        students = Student.query.filter(
            Student.name.ilike(f'%{query}%')
        ).limit(10).all()

        results = []
        for student in students:
            # Check if blacklisted
            try:
                is_blacklisted = Blacklist.query.filter_by(
                    student_id=student.id,
                    is_active=True
                ).first() is not None
            except Exception:
                is_blacklisted = False

            results.append({
                'id': student.id,
                'name': student.name,
                'program': student.program,
                'is_blacklisted': is_blacklisted
            })

        return jsonify(results), 200
    except Exception as e:
        import traceback
        current_app.logger.error(f"Error in search_students: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Search failed: {str(e)}'
        }), 500
    
# ============================================
# STUDENT API ENDPOINTS
# ============================================

@main.route('/api/students', methods=['GET'])
@login_required
def get_students():
    """
    Get paginated list of students with search and filters.
    
    Query Parameters:
        page (int): Page number (default: 1)
        per_page (int): Items per page (default: 20)
        search (str): Search query (name, email, phone, classroom, hall, ID)
        program (str): Filter by program
        hall (str): Filter by hall
        
    Returns:
        JSON: {
            success: bool,
            students: list,
            total: int,
            pages: int
        }
    """
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Cap per_page to prevent memory issues
        if per_page > 2000:
            per_page = 2000

        # Get and sanitize search query
        search_arg = request.args.get('search', '')
        search = sanitize_search_query(search_arg.strip()) if search_arg else ""
        
        # Start with base query
        query = Student.query
        
        # Apply search filter (if provided)
        if search:
            query = query.filter(
                or_(
                    Student.name.ilike(f'%{search}%'),
                    Student.email.ilike(f'%{search}%'),
                    Student.class_room.ilike(f'%{search}%'),
                    Student.hall.ilike(f'%{search}%'),
                    Student.phone.ilike(f'%{search}%'),
                    Student.id.cast(db.String).ilike(f'%{search}%')
                )
            )
        
        # Apply program filter
        program = request.args.get('program')
        if program:
            query = query.filter(Student.program == program)
        
        # Apply hall filter
        hall = request.args.get('hall')
        if hall:
            query = query.filter(Student.hall == hall)
        
        # Order by enrollment year (descending) then name (ascending)
        # Use nulls_last for better ordering if some years are missing
        query = query.order_by(
            Student.enrollment_year.desc(), 
            Student.name.asc()
        )
        
        # Paginate results
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        if not pagination:
            return jsonify({
                'success': True,
                'students': [],
                'total': 0,
                'pages': 0
            })

        # Safe serialization
        students_list = []
        for s in pagination.items:
            try:
                students_list.append(s.to_dict())
            except Exception as e:
                current_app.logger.warning(f"Failed to serialize student {getattr(s, 'id', 'unknown')}: {e}")

        return jsonify({
            'success': True,
            'students': students_list,
            'total': getattr(pagination, 'total', 0),
            'pages': getattr(pagination, 'pages', 0)
        })
        
    except Exception as e:
        import traceback
        current_app.logger.error(f"Error fetching students: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'An error occurred while fetching students: {str(e)}'
        }), 500


@main.route('/api/students/<int:id>', methods=['GET'])
@login_required
def get_single_student(id):
    """
    Get single student by ID.
    
    Required for View/Edit modals in frontend.
    
    Args:
        id (int): Student ID
        
    Returns:
        JSON: {success: bool, student: dict}
    """
    try:
        student = Student.query.get_or_404(id)
        
        # Check permissions
        if not student.has_permission(current_user):
            return jsonify({'error': 'Unauthorized'}), 403
        
        return jsonify({
            'success': True,
            'student': student.to_dict()
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching student {id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Student not found'
        }), 404


@main.route('/api/students', methods=['POST'])
@login_required
def create_student():
    """
    Create new student record.
    
    Supports multipart/form-data for photo uploads.
    Validates all input fields before creating record.
    
    Returns:
        JSON: {success: bool,student: dict} or {error: str}
    """
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        
        # Validate required fields
        name = data.get('name', '').strip()
        is_valid, error = validate_text_length(name, min_length=1, max_length=100, field_name="Name")
        if not is_valid:
            return jsonify({'error': error}), 400
        
        # Validate and normalize hall selection
        hall = data.get('hall', '').strip()
        if hall and hall not in VALID_HALLS:
            hall = None  # Ignore invalid hall, don't reject entire submission
        
        # Validate and normalize program selection
        program = data.get('program', '').strip()
        if program and program not in VALID_PROGRAMS:
            program = None  # Ignore invalid program
        
        # Validate optional email
        email = data.get('email', '').strip()
        if email and not validate_email(email):
            return jsonify({'error': 'Invalid email address'}), 400
        
        # Validate optional phone
        phone = data.get('phone', '').strip()
        if phone and not validate_phone(phone):
            return jsonify({'error': 'Invalid phone number format'}), 400
        
        # Validate optional guardian phone
        guardian_phone = data.get('guardian_phone', '').strip()
        if guardian_phone and not validate_phone(guardian_phone):
            return jsonify({'error': 'Invalid guardian phone number format'}), 400
        
        # Process photo upload (if provided)
        photo_url = None
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename:
                try:
                    photo_url = process_image(file)
                except Exception as e:
                    return jsonify({'error': str(e)}), 400
        
        # Parse date of birth
        dob = None
        dob_string = data.get('date_of_birth')
        if dob_string:
            is_valid, dob, error = validate_date_of_birth(dob_string)
            if not is_valid:
                return jsonify({'error': error}), 400
        
        # Generate face encoding if photo is provided
        face_encoding = None
        if photo_url:
            try:
                encoding = FaceHandler.get_encoding(photo_url)
                if encoding:
                    face_encoding = json.dumps(encoding)
            except Exception as e:
                current_app.logger.warning(f"Could not generate face encoding: {e}")

        # Create new student record
        new_student = Student(
            name=name,
            gender=data.get('gender'),
            program=program,
            hall=hall,
            class_room=data.get('class_room'),
            email=email or None,
            phone=phone or None,
            guardian_name=data.get('guardian_name'),
            guardian_phone=guardian_phone or None,
            date_of_birth=dob,
            enrollment_year=int(data.get('enrollment_year', datetime.now().year)),
            photo_file=photo_url,
            face_encoding=face_encoding,
            created_by=getattr(current_user, 'id', 1) # Fallback for internal secret auth
        )
        
        db.session.add(new_student)
        db.session.flush()  # Get ID before committing
        
        # Create initial academic record
        academic_record = AcademicRecord(
            student_id=new_student.id,
            form=new_student.current_form,
            year=new_student.enrollment_year
        )
        db.session.add(academic_record)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'student': new_student.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating student: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to create student record'
        }), 500


@main.route('/api/students/<int:id>', methods=['PUT'])
@login_required
def update_student(id):
    """
    Update existing student record.
    
    Args:
        id (int): Student ID
        
    Returns:
        JSON: {success: bool, photo_url: str} or {error: str}
    """
    try:
        student = Student.query.get_or_404(id)
        
        # Check permissions
        if not student.has_permission(current_user):
            return jsonify({'error': 'Unauthorized'}), 403
        
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        
        # Update photo if provided
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename:
                try:
                    photo_url = process_image(file)
                    student.photo_file = photo_url
                    # Update face encoding
                    encoding = FaceHandler.get_encoding(photo_url)
                    if encoding:
                        student.face_encoding = json.dumps(encoding)
                    else:
                        student.face_encoding = None
                except Exception as e:
                    return jsonify({'error': str(e)}), 400
        
        # Validate and update fields
        updateable_fields = [
            'name', 'gender', 'program', 'hall', 'class_room', 
            'guardian_name'
        ]
        
        for field in updateable_fields:
            if field in data:
                value = data[field].strip() if data[field] else None
                setattr(student, field, value)
        
        # Validate and update email
        if 'email' in data:
            email = data['email'].strip()
            if email and not validate_email(email):
                return jsonify({'error': 'Invalid email address'}), 400
            student.email = email or None
        
        # Validate and update phone numbers
        if 'phone' in data:
            phone = data['phone'].strip()
            if phone and not validate_phone(phone):
                return jsonify({'error': 'Invalid phone number'}), 400
            student.phone = phone or None
        
        if 'guardian_phone' in data:
            guardian_phone = data['guardian_phone'].strip()
            if guardian_phone and not validate_phone(guardian_phone):
                return jsonify({'error': 'Invalid guardian phone number'}), 400
            student.guardian_phone = guardian_phone or None
        
        # Update date of birth
        if 'date_of_birth' in data:
            dob_string = data['date_of_birth']
            if dob_string:
                is_valid, dob, error = validate_date_of_birth(dob_string)
                if not is_valid:
                    return jsonify({'error': error}), 400
                student.date_of_birth = dob
        
        # Update timestamp
        student.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'photo_url': student.to_dict()['photo_url']
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating student {id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to update student record'
        }), 500


# ============================================
# DATA MANAGEMENT
# ============================================

@main.route('/api/students/move-form', methods=['POST'])
@login_required
def bulk_move_form():
    """
    Bulk promote/demote students to different form levels.
    
    Updates enrollment year to match target form.
    
    Request JSON:
        ids: list of student IDs
        target_form: target form level
        
    Returns:
        JSON: {success: bool, message: str}
    """
    try:
        data = request.get_json()
        ids = data.get('ids', [])
        target = data.get('target_form')
        
        if not ids or not target:
            return jsonify({'error': 'Missing required data'}), 400
        
        current_year = datetime.now().year
        year_map = {
            "Form 1": current_year,
            "Form 2": current_year - 1,
            "Form 3": current_year - 2,
            "Completed": current_year - 3
        }
        
        new_year = year_map.get(target)
        if not new_year:
            return jsonify({'error': 'Invalid target form'}), 400
        
        # Fetch and update students individually to handle classroom prefix logic and history
        from models import AcademicRecord
        students = Student.query.filter(Student.id.in_(ids)).all()
        
        for s in students:
            s.enrollment_year = new_year
            
            # 1. Update specific classroom prefix (e.g., "1-SCI-1" -> "2-SCI-1")
            # This makes the change immediately visible in the data table
            if s.class_room and '-' in s.class_room:
                parts = s.class_room.split('-', 1)
                # target is "Form 1", "Form 2", "Form 3", or "Completed"
                if target.startswith("Form"):
                    form_num = target.split(' ')[-1] # Extracts "1", "2", or "3"
                    s.class_room = f"{form_num}-{parts[1]}"
                elif target == "Completed":
                    s.class_room = f"G-{parts[1]}" # 'G' for Graduated
            
            # 2. Add an academic record for the new form level
            # This ensures they have a record to store grades/remarks for their new form
            new_record = AcademicRecord(
                student_id=s.id,
                form=target,
                year=datetime.now().year
            )
            db.session.add(new_record)
        
        db.session.commit()
        
        # Log bulk operation
        log_bulk_operation(
            user_id=current_user.id,
            operation_type='promote',
            count=len(ids),
            success_count=len(ids)
        )
        
        return jsonify({
            'success': True,
            'message': f'Successfully moved {len(ids)} students to {target}.'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Bulk move error: {e}")
        return jsonify({
            'success': False,
            'error': 'Bulk operation failed'
        }), 500

@main.route('/api/students/bulk-action', methods=['POST'])
@login_required
def bulk_action():
    """Unified bulk action endpoint for Node.js proxy"""
    try:
        data = request.get_json()
        ids = data.get('ids', [])
        action = data.get('action')
        payload = data.get('payload', {})

        if not ids or not action:
            return jsonify({'error': 'Missing required data'}), 400

        if action == 'delete':
            from models import AcademicRecord
            AcademicRecord.query.filter(AcademicRecord.student_id.in_(ids)).delete(synchronize_session=False)
            Student.query.filter(Student.id.in_(ids)).delete(synchronize_session=False)
            msg = f"Deleted {len(ids)} students"
        elif action == 'move-form':
            target = payload.get('newYear')
            current_year = datetime.now().year
            year_map = {"Form 1": current_year, "Form 2": current_year - 1, "Form 3": current_year - 2, "Completed": current_year - 3}
            new_year = year_map.get(target, target)
            Student.query.filter(Student.id.in_(ids)).update({Student.enrollment_year: new_year}, synchronize_session=False)
            msg = f"Moved {len(ids)} students to {target}"
        elif action == 'update-hall':
            hall = payload.get('hall')
            Student.query.filter(Student.id.in_(ids)).update({Student.hall: hall}, synchronize_session=False)
            msg = f"Updated hall for {len(ids)} students"
        elif action == 'update-program':
            program = payload.get('program')
            Student.query.filter(Student.id.in_(ids)).update({Student.program: program}, synchronize_session=False)
            msg = f"Updated program for {len(ids)} students"
        else:
            return jsonify({'error': 'Invalid action'}), 400

        db.session.commit()
        log_bulk_operation(user_id=current_user.id, operation_type=action, count=len(ids), success_count=len(ids))
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Bulk action error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students/bulk-update', methods=['POST'])
@login_required
def bulk_update():
    """Bulk update a specific field for multiple students"""
    try:
        data = request.get_json()
        ids = data.get('ids', [])
        field = data.get('field')
        value = data.get('value')
        
        if not ids or not field:
            return jsonify({'error': 'Missing required data'}), 400
            
        # Validate field and value
        if field not in ['hall', 'program', 'class_room']:
            return jsonify({'error': 'Invalid update field'}), 400
            
        Student.query.filter(Student.id.in_(ids)).update({field: value}, synchronize_session=False)
        db.session.commit()
        
        log_bulk_operation(
            user_id=current_user.id,
            operation_type=f'update_{field}',
            count=len(ids),
            success_count=len(ids)
        )
        
        return jsonify({
            'success': True, 
            'message': f'Successfully updated {field} for {len(ids)} students'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@main.route('/api/students/bulk-delete', methods=['POST'])
@login_required
def bulk_delete():
    """Delete multiple students at once"""
    try:
        data = request.get_json()
        ids = data.get('ids', [])
        
        if not ids:
            return jsonify({'error': 'No students selected'}), 400
            
        # Delete academic records first (due to FK constraints if not CASCADE)
        # Assuming CASCASE is on, but let's be safe
        AcademicRecord.query.filter(AcademicRecord.student_id.in_(ids)).delete(synchronize_session=False)
        Student.query.filter(Student.id.in_(ids)).delete(synchronize_session=False)
        
        db.session.commit()
        
        log_bulk_operation(
            user_id=current_user.id,
            operation_type='delete',
            count=len(ids),
            success_count=len(ids)
        )
        
        return jsonify({
            'success': True, 
            'message': f'Successfully deleted {len(ids)} students'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main.route('/api/students/bulk-email', methods=['POST'])
@login_required
def bulk_email():
    """Send emails to multiple students"""
    try:
        data = request.get_json()
        ids = data.get('ids', [])
        subject = data.get('subject', '').strip()
        message_text = data.get('message', '').strip()
        
        if not ids or not subject or not message_text:
            return jsonify({'error': 'Missing required data'}), 400
            
        students = Student.query.filter(Student.id.in_(ids)).all()
        emails = [s.email for s in students if s.email]
        
        if not emails:
            return jsonify({'error': 'None of the selected students have email addresses'}), 400
            
        # Send emails asynchronously
        from utils import send_async_email
        from flask_mail import Message
        
        app = current_app._get_current_object()
        
        # In a real app, we might want to send one email with BCC or individual emails
        # For this system, individual emails might be better for personalization later
        # But for now, let's send them in a loop or a single message with BCC
        
        msg = Message(
            subject,
            bcc=emails, # Use BCC for privacy
            body=f"{message_text}\n\n---\nSent via SchoolSync Pro"
        )
        
        thread = Thread(target=send_async_email, args=[app, msg])
        thread.start()
        
        log_bulk_operation(
            user_id=current_user.id,
            operation_type='email',
            count=len(emails),
            success_count=len(emails)
        )
        
        return jsonify({
            'success': True, 
            'message': f'Email queued for {len(emails)} students'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@main.route('/api/students/delete-all', methods=['POST'])
@login_required
def delete_all():
    """
    Delete all student records (requires password confirmation).
    
    Dangerous operation - requires super admin and password verification.
    
    Request JSON:
        password: admin password
        
    Returns:
        JSON: {success: bool, message: str}
    """
    if not current_user.is_super_admin:
        return jsonify({'error': 'Super admin required'}), 403
    
    data = request.get_json()
    password = data.get('password')
    
    if not current_user.check_password(password):
        return jsonify({'error': 'Incorrect password'}), 403
    
    try:
        # Get count before deletion
        count = Student.query.count()
        
        # Delete all
        AcademicRecord.query.delete()
        Student.query.delete()
        db.session.commit()
        
        # Log bulk deletion
        log_bulk_operation(
            user_id=current_user.id,
            operation_type='delete_all',
            count=count,
            success_count=count
        )
        
        return jsonify({
            'success': True,
            'message': f'Deleted {count} student records'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Delete all error: {e}")
        return jsonify({
            'success': False,
            'error': 'Delete operation failed'
        }), 500


@main.route('/api/students/<int:id>', methods=['DELETE'])
@login_required
def delete_student(id):
    """
    Delete single student record.
    
    Args:
        id (int): Student ID
        
    Returns:
        JSON: {success: bool}
    """
    try:
        student = Student.query.get_or_404(id)
        student_name = student.name
        
        # Check permissions
        if not student.has_permission(current_user):
            return jsonify({'error': 'Unauthorized'}), 403
        
        db.session.delete(student)
        db.session.commit()
        
        # Log deletion
        log_student_delete(current_user.id, id, student_name)
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Delete student error: {e}")
        return jsonify({
            'success': False,
            'error': 'Delete failed'
        }), 500


# ============================================
# IMPORT FUNCTION
# ============================================

@main.route('/api/import', methods=['POST'])
@login_required
def import_file():
    """
    Bulk import students from CSV or Excel file.
    
    Expected columns (case-insensitive, spaces become underscores):
        - name (required)
        - gender
        - program
        - hall
        - class_room
        - enrollment_year or year
        - email
        - phone
        - guardian_name
        - guardian_phone
        
    Returns:
        JSON: {
            success: bool,
            message: str,
            errors: list
        }
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    # Validate file
    is_valid, filename_or_error = validate_data_file(file)
    if not is_valid:
        return jsonify({'error': filename_or_error}), 400
    
    try:
        # Parse file based on extension
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        success_count = 0
        errors = []
        current_year = datetime.now().year
        
        # Normalize column names: lowercase, replace spaces with underscores
        df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
        
        # Process each row
        for i, row in df.iterrows():
            row_num = i + 2  # Excel row number (1-indexed + header)
            
            try:
                # Get and validate name (required)
                name = str(row.get('name', '')).strip()
                if not name or name.lower() == 'nan':
                    continue  # Skip empty rows
                
                # Get enrollment year
                year_val = row.get('enrollment_year') or row.get('year')
                try:
                    if year_val:
                        enrollment_year = int(float(year_val))
                        # Basic sanity check for year (e.g., between 2000 and current_year + 1)
                        if enrollment_year < 2000 or enrollment_year > current_year + 1:
                            raise ValueError(f"Invalid enrollment year: {enrollment_year}")
                    else:
                        enrollment_year = current_year
                except Exception as e:
                    errors.append(f"Row {row_num}: Invalid enrollment year ({year_val})")
                    continue
                
                # Create student record
                student = Student(
                    name=name,
                    gender=str(row.get('gender', '')).strip() or None,
                    program=str(row.get('program', '')).strip() or None,
                    hall=str(row.get('hall', '')).strip() or None,
                    class_room=str(row.get('class_room', '')).strip() or None,
                    email=str(row.get('email', '')).strip() or None,
                    phone=str(row.get('phone', '')).strip() or None,
                    guardian_name=str(row.get('guardian_name', '')).strip() or None,
                    guardian_phone=str(row.get('guardian_phone', '')).strip() or None,
                    enrollment_year=enrollment_year,
                    created_by=current_user.id
                )
                
                db.session.add(student)
                success_count += 1
                
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
        
        # Commit all successful imports
        if success_count > 0:
            db.session.commit()
            
            # Log bulk import
            log_bulk_operation(
                user_id=current_user.id,
                operation_type='import',
                count=len(df),
                success_count=success_count,
                error_count=len(errors)
            )
        
        return jsonify({
            'success': True,
            'message': f'Successfully imported {success_count} students.',
            'errors': errors
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Import error: {e}")
        return jsonify({
            'error': f'File parsing failed: {str(e)}'
        }), 500


# ============================================
# SETTINGS / PROFILE MANAGEMENT
# ============================================

@main.route('/settings/profile', methods=['POST'])
@login_required
def update_profile():
    """
    Update user profile information.
    
    Validates email and phone number formats.
    Prevents duplicate usernames.
    
    Returns:
        Redirect to settings page with flash message
    """
    try:
        changed_fields = []
        
        # Check for username change
        new_username = request.form.get('username', '').strip()
        if new_username != current_user.username:
            # Check if username is taken
            existing = User.query.filter_by(username=new_username).first()
            if existing:
                flash('Username is already taken', 'error')
                return redirect(url_for('main.settings'))
            current_user.username = new_username
            changed_fields.append('username')
        
        # Validate and update email
        new_email = request.form.get('email', '').strip()
        if new_email != current_user.email:
            if not validate_email(new_email):
                flash('Invalid email address format', 'error')
                return redirect(url_for('main.settings'))
            current_user.email = new_email
            changed_fields.append('email')
        
        # Validate and update phone
        new_phone = request.form.get('phone', '').strip()
        if new_phone != current_user.phone:
            if new_phone and not validate_phone(new_phone):
                flash('Invalid phone number format', 'error')
                return redirect(url_for('main.settings'))
            current_user.phone = new_phone or None
            changed_fields.append('phone')
        
        # Update full name
        new_full_name = request.form.get('full_name', '').strip()
        if new_full_name != current_user.full_name:
            current_user.full_name = new_full_name
            changed_fields.append('full_name')
        
        db.session.commit()
        
        # Log profile update
        if changed_fields:
            log_profile_update(current_user.id, changed_fields)
        
        flash('Profile updated successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Profile update error: {e}")
        flash(f'Update failed: {str(e)}', 'error')
    
    return redirect(url_for('main.settings'))


@main.route('/settings/2fa', methods=['POST'])
@login_required
def update_2fa():
    """
    Update two-factor authentication settings.
    
    Supports: email, app (TOTP), sms, or disabling 2FA.
    
    Returns:
        Redirect to settings page with flash message
    """
    try:
        method = request.form.get('2fa_method')
        old_method = current_user.two_factor_method
        
        if method == 'app':
            # Enable TOTP (Google Authenticator)
            secret = request.form.get('totp_secret')
            if secret:
                current_user.totp_secret = secret
                current_user.two_factor_method = 'app'
                
        elif method == 'email':
            # Enable email OTP
            current_user.two_factor_method = 'email'
            
        elif method == 'sms':
            # Enable SMS OTP (requires phone number)
            if not current_user.phone:
                flash('Please add a phone number first', 'error')
                return redirect(url_for('main.settings'))
            current_user.two_factor_method = 'sms'
            
        elif method == 'off':
            # Disable 2FA
            current_user.two_factor_method = None
            current_user.totp_secret = None
        
        db.session.commit()
        
        # Log 2FA change
        enabled = method != 'off'
        log_2fa_change(current_user.id, enabled, method if enabled else None)
        
        flash('2FA settings updated successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"2FA update error: {e}")
        flash(f'Update failed: {str(e)}', 'error')
    
    return redirect(url_for('main.settings'))


# ============================================
# TEMPLATE DOWNLOAD
# ============================================

@main.route('/api/download-template/<file_type>')
@login_required
def download_template(file_type):
    """
    Download CSV or Excel template for bulk import.
    
    Args:
        file_type (str): 'csv' or 'excel'
        
    Returns:
        File download
    """
    # Create comprehensive template with example data
    df = pd.DataFrame({
        'name': ['John Doe'],
        'gender': ['Male'],
        'program': ['General Science'],
        'hall': ['Alema Hall'],
        'class_room': ['1-Science-A'],
        'enrollment_year': [datetime.now().year],
        'email': ['john@example.com'],
        'phone': ['024XXXXXXX'],
        'guardian_name': ['Jane Doe'],
        'guardian_phone': ['020XXXXXXX']
    })
    
    output = io.BytesIO()
    
    if file_type == 'csv':
        df.to_csv(output, index=False)
        mimetype = 'text/csv'
        download_name = 'student_import_template.csv'
    else:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Students')
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        download_name = 'student_import_template.xlsx'
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype=mimetype,
        as_attachment=True,
        download_name=download_name
    )

# ============================================
# FACE RECOGNITION ROUTES
# ============================================

@main.route('/face-search')
@login_required
def face_search_page():
    """Display face search/recognition page."""
    return render_template('face_search.html')


@main.route('/api/face-search', methods=['POST'])
@login_required
def api_face_search():
    """
    Search for a student using face recognition.
    
    Request JSON:
        image: base64 encoded image string (data:image/jpeg;base64,...)
        
    Returns:
        JSON: {success: bool, match: bool, student: dict}
    """
    try:
        data = request.get_json()
        image_data = data.get('image')
        
        if not image_data:
            return jsonify({'success': False, 'error': 'No image data provided'}), 400
            
        # 1. Get encoding for the target image
        target_encoding = FaceHandler.get_encoding(image_data)
        
        if target_encoding is None:
            return jsonify({
                'success': True, 
                'match': False, 
                'message': 'No face detected in the image'
            })
            
        # 2. Get all students with face encodings
        students_with_faces = Student.query.filter(Student.face_encoding.isnot(None)).all()
        
        if not students_with_faces:
            return jsonify({
                'success': True, 
                'match': False, 
                'message': 'No students in database have face records'
            })
            
        # 3. Prepare known encodings
        known_encodings = []
        for s in students_with_faces:
            try:
                enc = json.loads(s.face_encoding)
                known_encodings.append({'id': s.id, 'encoding': enc})
            except:
                continue
                
        # 4. Find best match
        match_result = FaceHandler.find_match(known_encodings, target_encoding)
        
        if match_result:
            student = Student.query.get(match_result['id'])
            return jsonify({
                'success': True,
                'match': True,
                'student': student.to_dict(),
                'confidence': 1 - match_result['distance']
            })
            
        return jsonify({
            'success': True,
            'match': False,
            'message': 'No matching student found'
        })
        
    except Exception as e:
        current_app.logger.error(f"Face search error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@main.route('/api/students/<int:id>/update-face', methods=['POST'])
@login_required
def update_student_face(id):
    """
    Manually trigger face encoding update for a student.
    Uses the student's existing photo_file.
    """
    try:
        student = Student.query.get_or_404(id)
        
        if not student.photo_file:
            return jsonify({'success': False, 'error': 'Student has no photo'}), 400
            
        encoding = FaceHandler.get_encoding(student.photo_file)
        
        if encoding:
            student.face_encoding = json.dumps(encoding)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Face encoding updated'})
        else:
            return jsonify({'success': False, 'error': 'No face detected in profile photo'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
