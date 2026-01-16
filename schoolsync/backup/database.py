import sqlite3
from datetime import datetime

DB_NAME = "students.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    with get_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            gender TEXT,
            program TEXT,
            hall TEXT,
            class_room TEXT,
            enrollment_year INTEGER,
            form TEXT
        )
        """)

def calculate_form(enrollment_year):
    diff = datetime.now().year - enrollment_year
    if diff >= 3:
        return "Completed"
    if diff == 2:
        return "Third Form"
    if diff == 1:
        return "Second Form"
    return "First Form"

def add_student(data):
    form = calculate_form(data["enrollment_year"])
    with get_connection() as conn:
        conn.execute("""
        INSERT INTO students 
        (name, gender, program, hall, class_room, enrollment_year, form)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data["name"],
            data["gender"],
            data["program"],
            data["hall"],
            data["class_room"],
            data["enrollment_year"],
            form
        ))

def get_students():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM students").fetchall()

    updated = []
    for row in rows:
        correct_form = calculate_form(row[6])
        if row[7] != correct_form:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE students SET form=? WHERE id=?",
                    (correct_form, row[0])
                )
        updated.append(row)

    return updated