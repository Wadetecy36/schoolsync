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
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from utils import send_password_reset_email # Import the new function

main = Blueprint('main', __name__)

def permission_required(permission):
    """Decorator to check user permissions"""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.is_active:
                return jsonify({'success': False, 'error': 'Account disabled'}), 403
            
            if permission == 'super_admin' and not current_user.is_super_admin:
                return jsonify({'success': False, 'error': 'Super admin access required'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def validate_file(file):
    """Validate uploaded file for security"""
    if not file:
        return False, "No file provided"
    
    # Check filename
    filename = secure_filename(file.filename)
    if not filename:
        return False, "Invalid filename"
    
    # Check file extension
    allowed_extensions = {'csv', 'xlsx', 'xls'}
    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if file_ext not in allowed_extensions:
        return False, f"File type not allowed. Allowed: {', '.join(allowed_extensions)}"
    
    # Check file size (max 16MB)
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    
    if file_size > 16 * 1024 * 1024:
        return False, "File too large (max 16MB)"
    
    # Read first few bytes to check magic number
    file_content = file.read(2048)
    file.seek(0)
   
    # Use filetype to guess
    kind = filetype.guess(file_content)
    
    # CSV files are often detected as None (plain text)
    if kind is None:
        if file_ext == 'csv':
            return True, filename
        else:
            return False, "Could not determine file type"
            
    mime_type = kind.mime
    
    allowed_mime_types = {
         'text/csv',
        'text/plain',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/zip', # xlsx is basically a zip
    }
    
    if mime_type not in allowed_mime_types and file_ext != 'csv':
         return False, f"Invalid file type detected: {mime_type}"
    
    return True, filename

@main.route('/')
@login_required
def index():
    """Main dashboard view"""
    return render_template('index.html')

@main.route('/students')
@login_required
def students():
    """Student list view"""
    return render_template('students.html')

@main.route('/student/<int:id>')
@login_required
def student_detail(id):
    """Individual student profile"""
    student = Student.query.get_or_404(id)
    if not student.has_permission(current_user):
        return jsonify({'error': 'Unauthorized access'}), 403
    return render_template('student_detail.html', student=student)



@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        email = request.form.get('email').strip()
        user = User.query.filter_by(email=email).first()
        
        if user:
            send_password_reset_email(user.email)
            flash('An email has been sent with instructions to reset your password.', 'info')
            return redirect(url_for('auth.login'))
        else:
            # Security: Don't reveal if email exists or not
            flash('An email has been sent with instructions to reset your password.', 'info')
            
    return render_template('forgot_password.html')

@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    try:
        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600) # 1 Hour Expiry
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

# ============ API ENDPOINTS ============

@main.route('/api/students', methods=['GET'])
@login_required
def get_students():
    """Get all students with filtering and search"""
    try:
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '').strip()
        program_filter = request.args.get('program', '')
        hall_filter = request.args.get('hall', '')
        sort_by = request.args.get('sort', 'name')
        sort_order = request.args.get('order', 'asc')
        
        # Base query
        if current_user.is_super_admin:
            query = Student.query
        else:
            query = Student.query.filter_by(created_by=current_user.id)
        
        # Apply search filter
        if search:
            query = query.filter(
                or_(
                    Student.name.ilike(f'%{search}%'),
                    Student.program.ilike(f'%{search}%'),
                    Student.class_room.ilike(f'%{search}%'),
                    Student.hall.ilike(f'%{search}%'),
                    Student.email.ilike(f'%{search}%')
                )
            )
        
        # Apply filters
        if program_filter:
            query = query.filter_by(program=program_filter)
        if hall_filter:
            query = query.filter_by(hall=hall_filter)
        
        # Apply sorting
        if sort_by == 'name':
            order_by = Student.name.asc() if sort_order == 'asc' else Student.name.desc()
        elif sort_by == 'enrollment_year':
            order_by = Student.enrollment_year.asc() if sort_order == 'asc' else Student.enrollment_year.desc()
        elif sort_by == 'program':
            order_by = Student.program.asc() if sort_order == 'asc' else Student.program.desc()
        elif sort_by == 'created_at':
            order_by = Student.created_at.asc() if sort_order == 'asc' else Student.created_at.desc()
        else:
            order_by = Student.id.asc()
        
        query = query.order_by(order_by)
        
        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        students = pagination.items
        
        # Convert to dict
        result = [s.to_dict() for s in students]
        
        return jsonify({
            'success': True,
            'students': result,
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page,
            'per_page': per_page,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students', methods=['POST'])
@login_required
def create_student():
    """Create a new student"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({'success': False, 'error': 'Name is required'}), 400
        
        # Validate Program
        program = data.get('program')
        if program and program not in VALID_PROGRAMS:
             return jsonify({'success': False, 'error': f'Invalid Program. Must be: {", ".join(VALID_PROGRAMS)}'}), 400

        # Validate Hall
        hall = data.get('hall')
        if hall and hall not in VALID_HALLS:
             return jsonify({'success': False, 'error': 'Invalid Hall selected'}), 400

        # Validate email format
        if data.get('email'):
            import re
            email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_regex, data['email']):
                return jsonify({'success': False, 'error': 'Invalid email format'}), 400
        
        # Parse date of birth
        dob = None
        if data.get('date_of_birth'):
            try:
                dob = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
            except ValueError:
                pass # Allow saving without failing if date is weird, or return error

        # Create student
        student = Student(
            name=data['name'].strip(),
            gender=data.get('gender'),
            date_of_birth=dob,
            program=program,
            hall=hall,
            class_room=data.get('class_room'),
            enrollment_year=data.get('enrollment_year', datetime.now().year),
            email=data.get('email'),
            phone=data.get('phone'),
            guardian_name=data.get('guardian_name'),
            guardian_phone=data.get('guardian_phone'),
            created_by=current_user.id
        )
        
        db.session.add(student)
        db.session.flush()
        
        # Create initial academic record
        record = AcademicRecord(
            student_id=student.id,
            form=student.current_form,
            year=student.enrollment_year
        )
        db.session.add(record)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Student created successfully',
            'student': student.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students/<int:id>', methods=['PUT'])
@login_required
def update_student(id):
    """Update a student"""
    try:
        student = Student.query.get_or_404(id)
        
        if not student.has_permission(current_user):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        
        # Validation for Updates
        if 'program' in data and data['program'] not in VALID_PROGRAMS:
             return jsonify({'success': False, 'error': 'Invalid Program'}), 400
             
        if 'hall' in data and data['hall'] not in VALID_HALLS:
             return jsonify({'success': False, 'error': 'Invalid Hall'}), 400

        # Update fields
        update_fields = ['name', 'gender', 'program', 'hall', 'class_room', 
                        'email', 'phone', 'guardian_name', 'guardian_phone']
        
        for field in update_fields:
            if field in data:
                setattr(student, field, data[field])
        
        if 'date_of_birth' in data and data['date_of_birth']:
            try:
                student.date_of_birth = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
            except ValueError:
                pass
        
        student.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Student updated successfully',
            'student': student.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students/<int:id>', methods=['DELETE'])
@login_required
def delete_student(id):
    """Delete a student"""
    try:
        student = Student.query.get_or_404(id)
        if not student.has_permission(current_user):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        db.session.delete(student)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Student deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students/delete-all', methods=['POST'])
@login_required
def delete_all_students():
    """Securely delete all students"""
    try:
        data = request.get_json()
        password = data.get('password')

        if not password:
            return jsonify({'success': False, 'error': 'Password required'}), 400

        # Verify Admin Password
        if not current_user.check_password(password):
            return jsonify({'success': False, 'error': 'Incorrect password'}), 403

        # Delete all records
        try:
            num_records = AcademicRecord.query.delete()
            num_students = Student.query.delete()
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': f'Successfully deleted {num_students} students.'
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    """Get dashboard statistics"""
    try:
        if current_user.is_super_admin:
            total_students = Student.query.count()
            students = Student.query.all()
        else:
            total_students = Student.query.filter_by(created_by=current_user.id).count()
            students = Student.query.filter_by(created_by=current_user.id).all()
        
        form_counts = { 'First Form': 0, 'Second Form': 0, 'Third Form': 0, 'Completed': 0 }
        
        for student in students:
            form_counts[student.current_form] = form_counts.get(student.current_form, 0) + 1
        
        program_counts = {}
        for student in students:
            if student.program:
                program_counts[student.program] = program_counts.get(student.program, 0) + 1
        
        current_month = datetime.now().month
        current_year = datetime.now().year
        new_this_month = len([
            s for s in students 
            if s.created_at.month == current_month and s.created_at.year == current_year
        ])
        
        with_email = len([s for s in students if s.email])
        
        return jsonify({
            'success': True,
            'stats': {
                'total_students': total_students,
                'new_this_month': new_this_month,
                'with_email': with_email,
                'without_email': total_students - with_email,
                'by_form': form_counts,
                'by_program': program_counts
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/import')
@login_required
def import_page():
    return render_template('import.html')

@main.route('/api/import', methods=['POST'])
@login_required
def import_students():
    """Import students from CSV or Excel file"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        is_valid, message = validate_file(file)
        if not is_valid:
            return jsonify({'success': False, 'error': message}), 400
        
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower()
        
        try:
            if file_ext == 'csv':
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
        except Exception as e:
            return jsonify({'success': False, 'error': f'Error reading file: {str(e)}'}), 400
        
        required_columns = ['name']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return jsonify({'success': False, 'error': f'Missing: {", ".join(missing_columns)}'}), 400
        
        imported = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                name = str(row.get('name', '')).strip()
                if not name: continue
                
                # --- NEW VALIDATION: Check Hall/Program against valid lists ---
                hall = str(row.get('hall', '')).strip()
                if hall and hall not in VALID_HALLS:
                    hall = None # or raise Error "Invalid Hall"
                
                program = str(row.get('program', '')).strip()
                if program and program not in VALID_PROGRAMS:
                    program = None

                dob = None
                if 'date_of_birth' in row and not pd.isna(row['date_of_birth']):
                    try:
                        dob = pd.to_datetime(row['date_of_birth']).date()
                    except:
                        pass
                
                enrollment_year = datetime.now().year
                if 'enrollment_year' in row and not pd.isna(row['enrollment_year']):
                    try: enrollment_year = int(row['enrollment_year'])
                    except: pass
                
                email = None
                if 'email' in row and not pd.isna(row.get('email')):
                    email = str(row['email']).strip()
                
                student = Student(
                    name=name,
                    gender=str(row.get('gender', '')).strip() if not pd.isna(row.get('gender')) else None,
                    date_of_birth=dob,
                    program=program,
                    hall=hall,
                    class_room=str(row.get('class_room', '')).strip() if not pd.isna(row.get('class_room')) else None,
                    enrollment_year=enrollment_year,
                    email=email,
                    phone=str(row.get('phone', '')).strip() if not pd.isna(row.get('phone')) else None,
                    guardian_name=str(row.get('guardian_name', '')).strip() if not pd.isna(row.get('guardian_name')) else None,
                    guardian_phone=str(row.get('guardian_phone', '')).strip() if not pd.isna(row.get('guardian_phone')) else None,
                    created_by=current_user.id
                )
                
                db.session.add(student)
                db.session.flush()
                
                record = AcademicRecord(student_id=student.id, form=student.current_form, year=student.enrollment_year)
                db.session.add(record)
                
                imported += 1
                if imported % 50 == 0: db.session.commit()
                
            except Exception as e:
                errors.append(f'Row {index + 2}: {str(e)}')
                continue
        
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Successfully imported {imported} students',
            'imported': imported,
            'errors': errors[:10]
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/download-template/<file_type>')
@login_required
def download_template(file_type):
    """Download import template"""
    try:
        # Create template with sample data that MATCHES our valid options
        template_data = {
            'name': ['John Doe', 'Jane Smith'],
            'gender': ['Male', 'Female'],
            'date_of_birth': ['2005-01-15', '2006-03-20'],
            'program': ['General Science', 'Business'], # Updated to match VALID_PROGRAMS
            'hall': ['Alema Hall', 'Ellen Hall'],       # Updated to match VALID_HALLS
            'class_room': ['1-Science-1', '2-Business-3'],
            'email': ['john@example.com', 'jane@example.com'],
            'phone': ['0241234567', '0501234567'],
            'guardian_name': ['Mr. Doe', 'Mrs. Smith'],
            'guardian_phone': ['0241111111', '0502222222'],
            'enrollment_year': [2025, 2025]
        }
        
        df = pd.DataFrame(template_data)
        output = io.BytesIO()
        
        if file_type == 'csv':
            df.to_csv(output, index=False)
            output.seek(0)
            return send_file(output, mimetype='text/csv', as_attachment=True, download_name='student_import_template.csv')
        elif file_type == 'excel':
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Students')
            output.seek(0)
            return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='student_import_template.xlsx')
        else:
            return jsonify({'error': 'Invalid file type'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- SETTINGS ROUTES ---

@main.route('/settings', methods=['GET'])
@login_required
def settings():
    return render_template('settings.html')

@main.route('/settings/profile', methods=['POST'])
@login_required
def update_profile():
    try:
        new_username = request.form.get('username').strip()
        new_email = request.form.get('email').strip()
        new_fullname = request.form.get('full_name').strip()
        new_phone = request.form.get('phone').strip()

        # Check for duplicates
        if new_username != current_user.username:
            if User.query.filter_by(username=new_username).first():
                flash('Username already taken.', 'error')
                return redirect(url_for('main.settings'))

        if new_email != current_user.email:
            if User.query.filter_by(email=new_email).first():
                flash('Email already registered.', 'error')
                return redirect(url_for('main.settings'))

        current_user.username = new_username
        current_user.full_name = new_fullname
        current_user.email = new_email
        current_user.phone = new_phone
        
        db.session.commit()
        flash('Profile credentials updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'System Error: {str(e)}', 'error')
        
    return redirect(url_for('main.settings'))

@main.route('/settings/2fa', methods=['POST'])
@login_required
def update_2fa():
    method = request.form.get('2fa_method')
    
    if method == 'sms' and not current_user.phone:
        flash('Please add a phone number before enabling SMS 2FA', 'warning')
        return redirect(url_for('main.settings'))
        
    if method == 'off':
        current_user.two_factor_method = None
    else:
        current_user.two_factor_method = method
        
    db.session.commit()
    flash(f'Two-Factor Authentication updated to: {method.upper() if method else "Disabled"}', 'success')
    return redirect(url_for('main.settings'))