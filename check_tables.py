from app import create_app
from extensions import db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    print("Tables:", inspector.get_table_names())
    for table in inspector.get_table_names():
        print(f"Columns in {table}:", [c['name'] for c in inspector.get_columns(table)])
