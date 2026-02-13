"""
Database migration to add blacklist table
Run this after adding the Blacklist model to models.py
"""

from app import app, db
from models import Blacklist

def create_blacklist_table():
    """Create the blacklist table"""
    with app.app_context():
        try:
            # Create the blacklist table
            db.create_all()
            print("✅ Blacklist table created successfully!")
            
            # Verify the table exists
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            if 'blacklist' in tables:
                print("✅ Verified: 'blacklist' table exists in database")
                
                # Show columns
                columns = inspector.get_columns('blacklist')
                print("\n📋 Blacklist table columns:")
                for col in columns:
                    print(f"  - {col['name']} ({col['type']})")
            else:
                print("❌ Error: 'blacklist' table not found!")
                
        except Exception as e:
            print(f"❌ Error creating table: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    print("🚀 Running blacklist table migration...")
    create_blacklist_table()
