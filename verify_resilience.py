from app import create_app
from extensions import db
from models import Student
import json

def test_resilience():
    app = create_app()
    with app.app_context():
        print("Testing Student.to_dict resilience...")
        students = Student.query.all()
        for s in students:
            try:
                d = s.to_dict()
                print(f"✓ Student {s.id} ({s.name}) serialized successfully")
            except Exception as e:
                print(f"❌ Student {s.id} ({s.name}) failed serialization: {e}")
                import traceback
                traceback.print_exc()

        print("\nVerification complete.")

if __name__ == "__main__":
    test_resilience()
