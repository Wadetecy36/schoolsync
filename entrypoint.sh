#!/bin/sh

# Apply database migrations
echo "Runnning database migrations..."
flask db upgrade

# Initialize database (safe to run multiple times)
echo "Initializing database..."
flask init-db

# Start the application
echo "Starting application..."
exec gunicorn app:app --bind 0.0.0.0:$PORT