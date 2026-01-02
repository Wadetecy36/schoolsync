from flask import Blueprint, render_template, request, jsonify, send_file, redirect, url_for, flash
from models import db, Student, AcademicRecord, User, VALID_HALLS, VALID_PROGRAMS
from datetime import datetime
from sqlalchemy import or_, and_
from flask_login import login_required, current_user
from functools import wraps
import pandas as pd
import io
import os
import filetype
from werkzeug.utils import secure_filename
import pyotp # Add this import at the top
from utils import generate_qr_code, get_totp_uri # Add these

main = Blueprint('main', __name__)

# --- Helper Functions ---
def validate_file(file):
    if not file: return False, "No file provided"
    filename = secure_filename(file.filename)
    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if file_ext not in {'csv', 'xlsx', 'xls'}:
        return False, "File type not allowed"
    
    file.seek(0, 2)
    if file.tell() > 16 * 1024 * 1024:
        return False, "File too large (max 16MB)"
    file.seek(0)
    
    kind = filetype.guess(file.read(2048))
    file.seek(0)

    if kind is None:
        if file_ext == 'csv': return True, filename
        return False, "Unknown file type"
        
    if kind.mime not in {
        'text/csv', 'text/plain',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/zip'
    } and file_ext != 'csv':
        return False, "Invalid file format"

    return True, filename

def permission_required(permission):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if permission == 'super_admin' and not current_user.is_super_admin:
                return jsonify({'error': 'Admin required'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Views ---
@main.route('/')
@login_required
def index():
    return render_template('index.html')

@main.route('/students')
@login_required
def students():
    return render_template('students.html')

@main.route('/student/<int:id>')
@login_required
def student_detail(id):
    student = Student.query.get_or_404(id)
    return render_template('student_detail.html', student=student)

@main.route('/import')
@login_required
def import_page():
    return render_template('import.html')


@main.route('/settings', methods=['GET'])
@login_required
def settings():
    # Logic for Authenticator App Setup
    qr_code = None
    secret = None
    
    # If they are enabling App 2FA, generate a temporary secret to show QR
    if not current_user.totp_secret:
        # Generate a temporary secret just for display
        # We save this to DB only when they confirm
        temp_secret = pyotp.random_base32()
        # Hack: temporarily attach to user to generate URI (not saved to DB yet)
        current_user.totp_secret = temp_secret
        uri, _ = get_totp_uri(current_user)
        qr_code = generate_qr_code(uri)
        secret = temp_secret
        # Don't save yet! Wait for them to select it.
    
    return render_template('settings.html', qr_code=qr_code, new_secret=secret)

# --- API Endpoints ---

@main.route('/api/students', methods=['GET'])
@login_required
def get_students():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '').strip()
        
        query = Student.query
        
        if search:
            query = query.filter(
                or_(
                    Student.name.ilike(f'%{search}%'),
                    Student.email.ilike(f'%{search}%'),
                    Student.phone.ilike(f'%{search}%'),
                    Student.id.cast(db.String).ilike(f'%{search}%')
                )
            )
        
        # Filtering
        if request.args.get('program'):
            query = query.filter(Student.program == request.args.get('program'))
        if request.args.get('hall'):
            query = query.filter(Student.hall == request.args.get('hall'))
        
        # Sort by recently added
        query = query.order_by(Student.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'success': True,
            'students': [s.to_dict() for s in pagination.items],
            'total': pagination.total,
            'pages': pagination.pages
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students', methods=['POST'])
@login_required
def create_student():
    try:
        data = request.get_json()
        
        if not data.get('name'):
            return jsonify({'error': 'Name is required'}), 400

        # Optional: Validate Hall/Program if strict mode desired
        
        student = Student(
            name=data['name'],
            gender=data.get('gender'),
            program=data.get('program'),
            hall=data.get('hall'),
            class_room=data.get('class_room'),
            email=data.get('email'),
            phone=data.get('phone'),
            guardian_name=data.get('guardian_name'),
            guardian_phone=data.get('guardian_phone'),
            date_of_birth=datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date() if data.get('date_of_birth') else None,
            enrollment_year=datetime.now().year,
            created_by=current_user.id
        )
        
        db.session.add(student)
        db.session.commit()
        return jsonify({'success': True, 'student': student.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students/<int:id>', methods=['PUT'])
@login_required
def update_student(id):
    student = Student.query.get_or_404(id)
    try:
        data = request.get_json()
        
        # Fields to update
        for field in ['name', 'gender', 'program', 'hall', 'class_room', 'email', 'phone', 'guardian_name', 'guardian_phone']:
            if field in data:
                setattr(student, field, data[field])

        if data.get('date_of_birth'):
            student.date_of_birth = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
            
        student.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students/<int:id>', methods=['DELETE'])
@login_required
def delete_student(id):
    student = Student.query.get_or_404(id)
    db.session.delete(student)
    db.session.commit()
    return jsonify({'success': True})

@main.route('/api/students/delete-all', methods=['POST'])
@login_required
def delete_all():
    pwd = request.json.get('password')
    if not current_user.check_password(pwd):
        return jsonify({'error': 'Incorrect Password'}), 403
        
    Student.query.delete()
    db.session.commit()
    return jsonify({'success': True, 'message': 'All students deleted'})

@main.route('/api/import', methods=['POST'])
@login_required
def import_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    
    file = request.files['file']
    is_valid, msg = validate_file(file)
    if not is_valid: return jsonify({'error': msg}), 400

    try:
        # Load File
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        success_count = 0
        errors = []

        # Iterate rows
        for idx, row in df.iterrows():
            try:
                name = str(row.get('name', '')).strip()
                if not name: continue

                # Basic validation
                student = Student(
                    name=name,
                    gender=row.get('gender'),
                    program=row.get('program'),
                    hall=row.get('hall'),
                    class_room=row.get('class_room'),
                    email=row.get('email'),
                    enrollment_year=datetime.now().year,
                    created_by=current_user.id
                )
                db.session.add(student)
                success_count += 1
            except Exception as e:
                errors.append(f"Row {idx+2}: {str(e)}")

        db.session.commit()
        return jsonify({
            'success': True,
            'message': f"Imported {success_count} students.",
            'errors': errors[:5] # Limit errors
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@main.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    total = Student.query.count()
    # Simple aggregations
    progs = db.session.query(Student.program, db.func.count(Student.id)).group_by(Student.program).all()
    prog_dict = {p[0]: p[1] for p in progs if p[0]}
    
    return jsonify({
        'success': True,
        'stats': {
            'total_students': total,
            'new_this_month': 0, # Implement date logic if needed
            'by_form': {},
            'by_program': prog_dict
        }
    })

# --- Settings Logic ---
@main.route('/settings/profile', methods=['POST'])
@login_required
def update_profile():
    try:
        current_user.full_name = request.form.get('full_name')
        current_user.username = request.form.get('username')
        current_user.email = request.form.get('email')
        current_user.phone = request.form.get('phone')
        db.session.commit()
        flash('Profile updated', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('main.settings'))

@main.route('/settings/2fa', methods=['POST'])
@login_required
def update_2fa():
    try:
        method = request.form.get('2fa_method')
        
        # --- LOGIC FOR GOOGLE AUTH (APP) ---
        if method == 'app':
            # Only save the secret if one was provided in the hidden form
            # (Meaning they scanned a NEW QR code)
            secret = request.form.get('totp_secret')
            if secret:
                current_user.totp_secret = secret
                current_user.two_factor_method = 'app'
                current_user.phone = None # Clean up phone if switching
            else:
                # If no new secret, they are just re-enabling it
                if current_user.totp_secret:
                    current_user.two_factor_method = 'app'
        
        # --- LOGIC FOR EMAIL ---
        elif method == 'email':
            current_user.two_factor_method = 'email'
        
        # --- LOGIC FOR SMS ---
        elif method == 'sms':
            if not current_user.phone:
                flash('Please save your phone number first!', 'warning')
                return redirect(url_for('main.settings'))
            current_user.two_factor_method = 'sms'

        # --- LOGIC FOR OFF ---
        elif method == 'off':
            current_user.two_factor_method = None
            current_user.totp_secret = None # Reset for security
        
        db.session.commit()
        
        status = current_user.two_factor_method.upper() if current_user.two_factor_method else "DISABLED"
        flash(f'Security settings updated: 2FA is now {status}', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating 2FA: {str(e)}', 'error')

    return redirect(url_for('main.settings'))
@main.route('/api/download-template/<fmt>')
def download_template(fmt):
    # (Simplified for brevity - your previous code here works)
    pass