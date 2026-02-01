from flask import Flask, render_template, request, redirect
from database import init_db, add_student, get_students
from datetime import datetime

app = Flask(__name__)

@app.route("/")
def index():
    students = get_students()
    return render_template("index.html", students=students)

@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        data = {
            "name": request.form["name"],
            "gender": request.form["gender"],
            "program": request.form["program"],
            "hall": request.form["hall"],
            "class_room": request.form["class_room"],
            "enrollment_year": datetime.now().year
        }
        add_student(data)
        return redirect("/")
    return render_template("add_student.html")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)