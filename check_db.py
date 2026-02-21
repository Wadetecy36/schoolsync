from app import create_app
from models import Student
from extensions import db

app = create_app()
with app.app_context():
    students = Student.query.all()
    enc_count = sum(1 for s in students if s.face_encoding)
    print(f"Total students: {len(students)}")
    print(f"Students with encodings: {enc_count}")
    if enc_count > 0:
        for s in students:
            if s.face_encoding:
                print(f" - ID: {s.id}, Name: {s.name}, Encoding sample: {str(s.face_encoding)[:100]}...")
