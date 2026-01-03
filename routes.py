from flask import Blueprint, render_template, request, jsonify, send_file, redirect, url_for, flash, current_app
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
import pyotp 
import cloudinary
import cloudinary.uploader
from utils import generate_qr_code, get_totp_uri 

main = Blueprint('main', __name__)

# --- Cloudinary Config ---
if os.environ.get('CLOUDINARY_CLOUD_NAME'):
    cloudinary.config(
        cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key = os.environ.get('CLOUDINARY_API_KEY'),
        api_secret = os.environ.get('CLOUDINARY_API_SECRET'),
        secure = True
    )

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

def upload_image(file):
    """Handles upload to Cloudinary (Prod) or Local (Dev)"""
    try:
        # Production: Cloudinary
        if os.environ.get('CLOUDINARY_CLOUD_NAME'):
            upload_result = cloudinary.uploader.upload(file)
            return upload_result['secure_url']
        
        # Local Development: Filesystem
        filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
        if not os.path.exists(current_app.config['UPLOAD_FOLDER']):
            os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
        file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
        return filename
    except Exception as e:
        print(f"Upload failed: {e}")
        return None

def validate_file(file):
    if not file: return False, "No file provided"
    filename = secure_filename(file.filename)
    if not (filename.endswith('.csv') or filename.endswith('.xlsx') or filename.endswith('.xls')):
         return False, "File type not allowed"
    
    file.seek(0, 2)
    if file.tell() > 16 * 1024 * 1024:
        return False, "File too large (max 16MB)"
    file.seek(0)
    
    # We trust extension check for imports for speed/compatibility
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
def index(): return render_template('index.html')

@main.route('/students')
@login_required
def students(): return render_template('students.html')

@main.route('/import')
@login_required
def import_page(): return render_template('import.html')

@main.route('/settings', methods=['GET'])
@login_required
def settings():
    qr_code = None
    secret = None
    # Use getattr for safety in case DB migration lags
    current_secret = getattr(current_user, 'totp_secret', None)
    
    if not current_secret:
        temp_secret = pyotp.random_base32()
        # Temp attach to generate URI
        current_user.totp_secret = temp_secret
        uri, _ = get_totp_uri(current_user)
        qr_code = generate_qr_code(uri)
        secret = temp_secret
    
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
                    Student.class_room.ilike(f'%{search}%'),
                    Student.hall.ilike(f'%{search}%'),
                    Student.phone.ilike(f'%{search}%'),
                    Student.id.cast(db.String).ilike(f'%{search}%')
                )
            )
        
        # Sidebar Filters
        if request.args.get('program'):
            query = query.filter(Student.program == request.args.get('program'))
        if request.args.get('hall'):
            query = query.filter(Student.hall == request.args.get('hall'))
        
        query = query.order_by(Student.enrollment_year.desc(), Student.name.asc())
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
        # Use request.form because it includes File Data + Text Data
        data = request.form
        
        if not data.get('name'):
            return jsonify({'error': 'Name is required'}), 400

        # Validate Hall & Program
        hall = data.get('hall')
        if hall and hall not in VALID_HALLS: hall = None 

        program = data.get('program')
        if program and program not in VALID_PROGRAMS: program = None

        # Image Upload Logic
        photo_result = None
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '' and allowed_file(file.filename):
                photo_result = upload_image(file)

        dob = None
        if data.get('date_of_birth'):
            try: dob = datetime.strptime(data.get('date_of_birth'), '%Y-%m-%d').date()
            except: pass

        student = Student(
            name=data.get('name'),
            gender=data.get('gender'),
            program=program,
            hall=hall,
            class_room=data.get('class_room'),
            email=data.get('email'),
            phone=data.get('phone'),
            guardian_name=data.get('guardian_name'),
            guardian_phone=data.get('guardian_phone'),
            date_of_birth=dob,
            enrollment_year=datetime.now().year,
            photo_file=photo_result,
            created_by=current_user.id
        )
        
        db.session.add(student)
        db.session.flush() # Generate ID
        
        # Add default academic record
        db.session.add(AcademicRecord(student_id=student.id, form=student.current_form, year=student.enrollment_year))
        
        db.session.commit()
        return jsonify({'success': True, 'student': student.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students/<int:id>', methods=['PUT'])
@login_required
def update_student(id):
    student = Student.query.get_or_404(id)
    if not student.has_permission(current_user): return jsonify({'error': 'Unauthorized'}), 403
    try:
        data = request.form
        
        # Photo Update
        if request.files and 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '' and allowed_file(file.filename):
                url = upload_image(file)
                if url: student.photo_file = url

        # Validation Logic for Hall/Prog
        if data.get('hall') and data['hall'] not in VALID_HALLS:
            return jsonify({'error': 'Invalid Hall selected'}), 400

        for field in ['name', 'gender', 'program', 'hall', 'class_room', 'email', 'phone', 'guardian_name', 'guardian_phone']:
            if field in data:
                setattr(student, field, data[field])

        if data.get('date_of_birth'):
             try: student.date_of_birth = datetime.strptime(data.get('date_of_birth'), '%Y-%m-%d').date()
             except: pass
            
        student.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students/move-form', methods=['POST'])
@login_required
def bulk_move_form():
    """Bulk promote students logic"""
    try:
        data = request.get_json()
        ids = data.get('ids', [])
        target = data.get('target_form')

        if not ids or not target: return jsonify({'error': 'Missing data'}), 400
        
        current_year = datetime.now().year
        year_map = {
            "Form 1": current_year,
            "Form 2": current_year - 1,
            "Form 3": current_year - 2,
            "Completed": current_year - 3
        }
        new_year = year_map.get(target)
        if not new_year: return jsonify({'error': 'Invalid target'}), 400

        Student.query.filter(Student.id.in_(ids)).update({Student.enrollment_year: new_year}, synchronize_session=False)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Promotions applied successfully.'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students/<int:id>', methods=['DELETE'])
@login_required
def delete_student(id):
    student = Student.query.get_or_404(id)
    db.session.delete(student); db.session.commit()
    return jsonify({'success': True})

@main.route('/api/students/delete-all', methods=['POST'])
@login_required
def delete_all():
    pwd = request.json.get('password')
    if not current_user.check_password(pwd): return jsonify({'error': 'Incorrect Password'}), 403
    AcademicRecord.query.delete(); Student.query.delete(); db.session.commit()
    return jsonify({'success': True, 'message': 'All students deleted'})

@main.route('/api/import', methods=['POST'])
@login_required
def import_file():
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    is_valid, msg = validate_file(file)
    if not is_valid: return jsonify({'error': msg}), 400

    try:
        if file.filename.endswith('.csv'): df = pd.read_csv(file)
        else: df = pd.read_excel(file)

        success = 0
        errors = []
        for i, row in df.iterrows():
            try:
                name = str(row.get('name','')).strip(); 
                if not name: continue
                
                hall = str(row.get('hall','')).strip()
                if hall not in VALID_HALLS: hall = None 
                
                program = str(row.get('program', '')).strip()
                if program not in VALID_PROGRAMS: program = None
                
                db.session.add(Student(
                    name=name, gender=row.get('gender'), 
                    program=program, hall=hall, 
                    class_room=str(row.get('class_room','')), email=str(row.get('email','')),
                    enrollment_year=datetime.now().year, created_by=current_user.id
                )); success += 1
            except Exception as e: errors.append(str(e))
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'Imported {success}', 'errors': errors[:5]})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- MISSING ROUTE FIX ---
@main.route('/api/students/<int:id>', methods=['GET'])
@login_required
def get_single_student(id):
    """Fetch single student data for View/Edit modals"""
    try:
        student = Student.query.get_or_404(id)
        
        # Check permissions
        if not student.has_permission(current_user):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403

        return jsonify({
            'success': True, 
            'student': student.to_dict()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
# -------------------------

@main.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    total = Student.query.count()
    progs = db.session.query(Student.program, db.func.count(Student.id)).group_by(Student.program).all()
    
    current_year = datetime.now().year
    form_counts = { 'First Form': 0, 'Second Form': 0, 'Third Form': 0, 'Completed': 0 }
    
    # Calculate Form distribution
    all_years = db.session.query(Student.enrollment_year).all()
    for (yr,) in all_years:
        diff = current_year - yr
        if diff >= 3: form_counts['Completed'] += 1
        elif diff == 2: form_counts['Third Form'] += 1
        elif diff == 1: form_counts['Second Form'] += 1
        else: form_counts['First Form'] += 1

    return jsonify({
        'success': True,
        'stats': {
            'total_students': total,
            'new_this_month': 0,
            'by_form': form_counts,
            'by_program': {p[0]: p[1] for p in progs if p[0]}
        }
    })

# --- SETTINGS / PROFILE Logic ---

@main.route('/settings/profile', methods=['POST'])
@login_required
def update_profile():
    try:
        new_username = request.form.get('username')
        if new_username != current_user.username:
            if User.query.filter_by(username=new_username).first():
                flash('Username taken', 'error')
                return redirect(url_for('main.settings'))
        
        # Verify Email uniqueness
        new_email = request.form.get('email')
        if new_email != current_user.email and User.query.filter_by(email=new_email).first():
            flash('Email taken', 'error')
            return redirect(url_for('main.settings'))

        current_user.full_name = request.form.get('full_name')
        current_user.username = new_username
        current_user.email = new_email
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
        
        # App 2FA logic
        if method == 'app':
            secret = request.form.get('totp_secret')
            if secret:
                current_user.totp_secret = secret
                current_user.two_factor_method = 'app'
                current_user.phone = None
            elif current_user.totp_secret:
                current_user.two_factor_method = 'app'
        
        # Email 2FA Logic
        elif method == 'email':
            current_user.two_factor_method = 'email'
        
        # Disabled Logic
        elif method == 'off':
            current_user.two_factor_method = None
            current_user.totp_secret = None
            
        db.session.commit()
        flash(f'2FA updated to: {current_user.two_factor_method}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('main.settings'))

@main.route('/api/download-template/<file_type>')
@login_required
def download_template(file_type):
    # Safe Download logic
    try:
        # Use simple sample data
        data = { 'name': ['John Doe'], 'program': ['General Science'] }
        df = pd.DataFrame(data)
        output = io.BytesIO()
        if file_type == 'csv':
            df.to_csv(output, index=False)
            mt, nm = 'text/csv', 'template.csv'
        else:
            with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False)
            mt, nm = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'template.xlsx'
        output.seek(0)
        return send_file(output, mimetype=mt, as_attachment=True, download_name=nm)
    except: return jsonify({'error': 'Error generating template'}), 500