from flask import Blueprint, render_template, request, jsonify, send_file, redirect, url_for, flash, current_app
from extensions import db
from models import Student, AcademicRecord, User, VALID_HALLS, VALID_PROGRAMS
from datetime import datetime
from sqlalchemy import or_, and_, func, text
from flask_login import login_required, current_user
from functools import wraps
import pandas as pd
import io
import os
from werkzeug.utils import secure_filename
import pyotp 
from utils import generate_qr_code, get_totp_uri 
# Cloudinary Removed - Switched to Base64
from PIL import Image
import base64

main = Blueprint('main', __name__)

# ... (omitted code) ...

@main.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    total = Student.query.count()
    current_year = datetime.now().year
    form_counts = { 'First Form': 0, 'Second Form': 0, 'Third Form': 0, 'Completed': 0 }
    
    # Optimized SQL Aggregation
    rows = db.session.query(Student.enrollment_year, func.count(Student.id))\
        .group_by(Student.enrollment_year).all()
        
    for year, count in rows:
        diff = current_year - year
        if diff >= 3: form_counts['Completed'] += count
        elif diff == 2: form_counts['Third Form'] += count
        elif diff == 1: form_counts['Second Form'] += count
        else: form_counts['First Form'] += count
        
    return jsonify({ 'success': True, 'stats': { 'total_students': total, 'new_this_month': 0, 'by_form': form_counts, 'by_program': {} } })
def migrate_db():
    try:
        # Run raw SQL to alter column type for Postgres
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE students ALTER COLUMN photo_file TYPE TEXT;"))
            conn.commit()
        return "Database Schema Updated Successfully! You can now upload images."
    except Exception as e:
        return f"Migration Error (Ignorable if already done): {e}"


# --- HELPER FUNCTIONS ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

def process_image(file):
    """Resize image and convert to Base64 string"""
    try:
        if not file: return None
        
        # Open image using Pillow
        img = Image.open(file)
        
        # Convert to RGB (in case of PNG with transparency)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        # Resize: maintain aspect ratio, max 400px width/height
        img.thumbnail((400, 400))
        
        # Save to buffer as JPEG
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=70) # Compress to reduce size
        buf.seek(0)
        
        # Encode to Base64
        b64_str = base64.b64encode(buf.getvalue()).decode('utf-8')
        return f"data:image/jpeg;base64,{b64_str}"
        
    except Exception as e:
        raise Exception(f"Image Processing Error: {str(e)}")

def validate_file(file):
    if not file: return False, "No file provided"
    filename = secure_filename(file.filename)
    if not (filename.endswith('.csv') or filename.endswith('.xlsx') or filename.endswith('.xls')):
         return False, "File type not allowed (CSV or Excel only)"
    return True, filename

# --- VIEWS ---
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
    qr_code = None; secret = None;
    current_secret = getattr(current_user, 'totp_secret', None)
    if not current_secret:
        temp_secret = pyotp.random_base32()
        current_user.totp_secret = temp_secret
        uri, _ = get_totp_uri(current_user)
        qr_code = generate_qr_code(uri)
        secret = temp_secret
    return render_template('settings.html', qr_code=qr_code, new_secret=secret)

# --- STUDENT API ENDPOINTS ---

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
        
        if request.args.get('program'): query = query.filter(Student.program == request.args.get('program'))
        if request.args.get('hall'): query = query.filter(Student.hall == request.args.get('hall'))
        
        query = query.order_by(Student.enrollment_year.desc(), Student.name.asc())
        pag = query.paginate(page=page, per_page=per_page, error_out=False)
        return jsonify({ 
            'success': True, 
            'students': [s.to_dict() for s in pag.items], 
            'total': pag.total, 
            'pages': pag.pages 
        })
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students/<int:id>', methods=['GET'])
@login_required
def get_single_student(id):
    """Required for View/Edit Modals"""
    try:
        student = Student.query.get_or_404(id)
        if not student.has_permission(current_user): return jsonify({'error':'Unauthorized'}), 403
        return jsonify({'success': True, 'student': student.to_dict()})
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students', methods=['POST'])
@login_required
def create_student():
    try:
        data = request.form
        if not data.get('name'): return jsonify({'error': 'Name is required'}), 400

        # Validate Hall/Program (Prevent Junk Data)
        hall = data.get('hall') if data.get('hall') in VALID_HALLS else None
        prog = data.get('program') if data.get('program') in VALID_PROGRAMS else None

        # Upload
        photo_url = None
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '': 
                photo_url = process_image(file)

        dob = None
        if data.get('date_of_birth'):
             try: dob = datetime.strptime(data.get('date_of_birth'), '%Y-%m-%d').date()
             except: pass

        new_s = Student(
            name=data.get('name'), gender=data.get('gender'),
            program=prog, hall=hall,
            class_room=data.get('class_room'), email=data.get('email'),
            phone=data.get('phone'), guardian_name=data.get('guardian_name'),
            guardian_phone=data.get('guardian_phone'), date_of_birth=dob,
            enrollment_year=datetime.now().year,
            photo_file=photo_url, 
            created_by=current_user.id
        )
        db.session.add(new_s); db.session.flush() 
        db.session.add(AcademicRecord(student_id=new_s.id, form=new_s.current_form, year=new_s.enrollment_year))
        db.session.commit()
        return jsonify({'success': True, 'student': new_s.to_dict()})
        
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
        
        # Photo Handling
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '':
                url = process_image(file)
                student.photo_file = url

        # Update fields
        for k in ['name', 'gender', 'program', 'hall', 'class_room', 'email', 'phone', 'guardian_name', 'guardian_phone']:
            if k in data: setattr(student, k, data[k])

        if data.get('date_of_birth'):
             try: student.date_of_birth = datetime.strptime(data.get('date_of_birth'), '%Y-%m-%d').date()
             except: pass
        
        student.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'photo_url': student.to_dict()['photo_url']})
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

# --- DATA MANAGEMENT ---

@main.route('/api/students/move-form', methods=['POST'])
@login_required
def bulk_move_form():
    try:
        data = request.get_json()
        ids = data.get('ids', []); target = data.get('target_form')
        if not ids or not target: return jsonify({'error': 'Missing data'}), 400
        
        cy = datetime.now().year
        y_map = { "Form 1": cy, "Form 2": cy-1, "Form 3": cy-2, "Completed": cy-3 }
        new_year = y_map.get(target)
        if not new_year: return jsonify({'error': 'Invalid target'}), 400

        Student.query.filter(Student.id.in_(ids)).update({Student.enrollment_year: new_year}, synchronize_session=False)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Promotions applied successfully.'})
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/students/delete-all', methods=['POST'])
@login_required
def delete_all():
    if not current_user.check_password(request.json.get('password')): return jsonify({'error': 'Incorrect Password'}), 403
    AcademicRecord.query.delete(); Student.query.delete(); db.session.commit(); 
    return jsonify({'success': True, 'message': 'All students deleted'})

@main.route('/api/students/<int:id>', methods=['DELETE'])
@login_required
def delete_student(id):
    student = Student.query.get_or_404(id)
    db.session.delete(student); db.session.commit()
    return jsonify({'success': True})

# --- IMPORT FUNCTION (FIXED MISSING 404) ---
@main.route('/api/import', methods=['POST'])
@login_required
def import_file():
    if 'file' not in request.files: return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    is_valid, msg = validate_file(file)
    if not is_valid: return jsonify({'error': msg}), 400

    try:
        if file.filename.endswith('.csv'): df = pd.read_csv(file)
        else: df = pd.read_excel(file)

        success = 0; errors = []
        current_year = datetime.now().year
        
        # Clean columns: strip spaces, lower case match
        df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

        for i, row in df.iterrows():
            row_num = i + 2 # Header is row 1
            try:
                name = str(row.get('name', '')).strip()
                if not name or name.lower() == 'nan': continue
                
                # Validation
                hall = str(row.get('hall', '')).strip()
                # Fuzzy match or leave as is? Let's leave as is but warn if not in list
                
                prog = str(row.get('program', '')).strip()
                
                # Year Handling
                year_val = row.get('enrollment_year') or row.get('year')
                try: enc_year = int(float(year_val)) if year_val else current_year
                except: enc_year = current_year

                student = Student(
                    name=name, 
                    gender=str(row.get('gender', '')), 
                    program=prog, 
                    hall=hall, 
                    class_room=str(row.get('class_room', '')), 
                    email=str(row.get('email', '')),
                    phone=str(row.get('phone', '')),
                    guardian_name=str(row.get('guardian_name', '')),
                    guardian_phone=str(row.get('guardian_phone', '')),
                    enrollment_year=enc_year, 
                    created_by=current_user.id
                )
                db.session.add(student)
                success += 1
            except Exception as e: 
                errors.append(f"Row {row_num}: {str(e)}")
        
        if success > 0: db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Successfully imported {success} students.', 
            'errors': errors # Send all errors
        })
    except Exception as e: return jsonify({'error': f"File Parse Error: {str(e)}"}), 500

# --- SETTINGS / STATS / TEMPLATE ---

@main.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    total = Student.query.count()
    current_year = datetime.now().year
    form_counts = { 'First Form': 0, 'Second Form': 0, 'Third Form': 0, 'Completed': 0 }
    
    # Simple form calculation
    # Optimized SQL Aggregation
    rows = db.session.query(Student.enrollment_year, func.count(Student.id))\
        .group_by(Student.enrollment_year).all()
        
    for year, count in rows:
        diff = current_year - year
        if diff >= 3: form_counts['Completed'] += count
        elif diff == 2: form_counts['Third Form'] += count
        elif diff == 1: form_counts['Second Form'] += count
        else: form_counts['First Form'] += count
        
    return jsonify({ 'success': True, 'stats': { 'total_students': total, 'new_this_month': 0, 'by_form': form_counts, 'by_program': {} } })

@main.route('/settings/profile', methods=['POST'])
@login_required
def update_profile():
    # Profile update logic
    try:
        if request.form.get('username') != current_user.username and User.query.filter_by(username=request.form.get('username')).first(): 
            flash('Username taken', 'error'); return redirect(url_for('main.settings'))
        
        current_user.full_name = request.form.get('full_name')
        current_user.username = request.form.get('username')
        current_user.email = request.form.get('email')
        current_user.phone = request.form.get('phone')
        db.session.commit()
        flash('Profile updated', 'success')
    except Exception as e: flash(f'Error: {e}', 'error')
    return redirect(url_for('main.settings'))

@main.route('/settings/2fa', methods=['POST'])
@login_required
def update_2fa():
    try:
        m = request.form.get('2fa_method')
        if m == 'app':
            s = request.form.get('totp_secret')
            if s: current_user.totp_secret = s; current_user.two_factor_method = 'app'
        elif m == 'email': current_user.two_factor_method = 'email'
        elif m == 'off': current_user.two_factor_method = None; current_user.totp_secret = None
        db.session.commit(); flash('2FA Settings Updated', 'success')
    except Exception as e: db.session.rollback(); flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('main.settings'))

@main.route('/api/download-template/<file_type>')
@login_required
def download_template(file_type):
    # Dummy template for testing
    # Comprehensive Template
    df = pd.DataFrame({
        'name': ['John Doe'], 
        'gender': ['Male'],
        'program': ['General Science'], 
        'hall': ['Alema Hall'],
        'class_room': ['1-Science-A'],
        'enrollment_year': [datetime.now().year],
        'email': ['john@example.com'],
        'phone': ['024xxxxxxx'],
        'guardian_name': ['Jane Doe'],
        'guardian_phone': ['020xxxxxxx']
    })
    output = io.BytesIO()
    if file_type == 'csv': df.to_csv(output, index=False); mt='text/csv'; nm='template.csv'
    else: 
        with pd.ExcelWriter(output, engine='openpyxl') as w: df.to_excel(w, index=False)
        mt='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'; nm='template.xlsx'
    output.seek(0)
    return send_file(output, mimetype=mt, as_attachment=True, download_name=nm)