import os
import sqlite3
from app import create_app
from extensions import db
from models import Student

app = create_app()
with app.app_context():
    total = Student.query.count()
    with_encoding = Student.query.filter(Student.face_encoding.isnot(None)).count()
    print(f"Total students: {total}")
    print(f"Students with Face ID encodings: {with_encoding}")
    
    if with_encoding > 0:
        s = Student.query.filter(Student.face_encoding.isnot(None)).first()
        print(f"Sample encoding (first 5 values): {s.face_encoding[:5] if s.face_encoding else 'None'}")
