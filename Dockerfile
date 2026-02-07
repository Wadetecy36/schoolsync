# Use official Python runtime as a parent image (Bookworm for stability)
FROM python:3.9-slim-bookworm

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

# Install system dependencies (needed for PostgreSQL adapter)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (optimize cache)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copy project files
COPY . /app/

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Expose port
EXPOSE 10000

# Start command
CMD ["./entrypoint.sh"]