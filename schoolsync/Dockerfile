# Use a lightweight Python version
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# 1. Copy ONLY requirements first (This allows Docker caching)
COPY requirements.txt .

# 2. Install dependencies (This layer is cached if requirements.txt doesn't change)
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy the rest of the app code
COPY . .

# 4. Command to run the app
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]