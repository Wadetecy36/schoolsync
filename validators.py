"""
Validation Utilities for SchoolSync Pro
========================================
Centralizes all input validation logic for the application.

Author: SchoolSync Team
Last Updated: 2026-01-16
"""

import re
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image
import io

# Security: Protect against Decompression Bomb
Image.MAX_IMAGE_PIXELS = 100000000  # 100M pixels (approx 10000x10000)



# ============================================
# EMAIL VALIDATION
# ============================================

def validate_email(email):
    """
    Validate email format using RFC-compliant regex.
    
    Args:
        email (str): Email address to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not email or len(email) > 120:
        return False
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


# ============================================
# PHONE NUMBER VALIDATION
# ============================================

def validate_phone(phone):
    """
    Validate phone number (Ghana/International format).
    
    Accepts formats:
    - 0XXXXXXXXX (Ghana local: 10 digits)
    - 233XXXXXXXXX (Ghana international: 12 digits)
    - +233XXXXXXXXX (Ghana with +: 13 chars)
    
    Args:
        phone (str): Phone number to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not phone:
        return True  # Optional field
    
    # Remove spaces, dashes, and parentheses
    clean = re.sub(r'[\s\-\(\)]', '', phone)
    
    # Ghana number patterns
    return re.match(r'^(0\d{9}|233\d{9}|\+233\d{9})$', clean) is not None


def normalize_phone(phone):
    """
    Normalize phone number to standard format.
    
    Args:
        phone (str): Phone number to normalize
        
    Returns:
        str: Normalized phone number or original if invalid
    """
    if not phone:
        return phone
    
    clean = re.sub(r'[\s\-\(\)]', '', phone)
    
    # Convert to international format if local
    if clean.startswith('0') and len(clean) == 10:
        return f"+233{clean[1:]}"
    elif clean.startswith('233') and len(clean) == 12:
        return f"+{clean}"
    
    return phone


# ============================================
# DATE VALIDATION
# ============================================

def validate_date(date_string, format='%Y-%m-%d'):
    """
    Validate and parse date string.
    
    Args:
        date_string (str): Date string to validate
        format (str): Expected date format (default: YYYY-MM-DD)
        
    Returns:
        tuple: (is_valid, date_object or None)
    """
    if not date_string:
        return False, None
    
    try:
        date_obj = datetime.strptime(date_string, format).date()
        return True, date_obj
    except (ValueError, TypeError):
        return False, None


def validate_date_of_birth(dob_string):
    """
    Validate date of birth (must be in the past, reasonable age range).
    
    Args:
        dob_string (str): Date of birth string (YYYY-MM-DD)
        
    Returns:
        tuple: (is_valid, date_object or None, error_message)
    """
    is_valid, date_obj = validate_date(dob_string)
    
    if not is_valid:
        return False, None, "Invalid date format. Use YYYY-MM-DD."
    
    today = datetime.now().date()
    age = today.year - date_obj.year - ((today.month, today.day) < (date_obj.month, date_obj.day))
    
    if date_obj >= today:
        return False, None, "Date of birth must be in the past."
    
    if age > 120:
        return False, None, "Invalid date of birth (too old)."
    
    if age < 5:
        return False, None, "Student must be at least 5 years old."
    
    return True, date_obj, None


# ============================================
# IMAGE VALIDATION
# ============================================

# Image constraints
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
MIN_IMAGE_DIMENSION = 50  # Minimum 50x50px
MAX_IMAGE_DIMENSION = 4000  # Maximum 4000x4000px
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def validate_image_file(file):
    """
    Validate uploaded image file.
    
    Checks:
    - File exists
    - File extension is allowed
    - File size is within limits
    - Image dimensions are reasonable
    
    Args:
        file: FileStorage object from Flask request
        
    Returns:
        tuple: (is_valid, error_message or None)
    """
    if not file or not file.filename:
        return False, "No file provided"
    
    # Check file extension
    filename = secure_filename(file.filename)
    if '.' not in filename:
        return False, "File must have an extension"
    
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return False, f"Invalid file type. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"
    
    # Check file size
    file.seek(0, 2)  # Seek to end
    size = file.tell()
    file.seek(0)  # Reset to beginning
    
    if size > MAX_IMAGE_SIZE:
        return False, f"File too large. Maximum size: {MAX_IMAGE_SIZE // (1024*1024)}MB"
    
    if size == 0:
        return False, "File is empty"
    
    # Validate image can be opened and check dimensions
    try:
        img = Image.open(file)
        width, height = img.size
        file.seek(0)  # Reset for later use
        
        if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
            return False, f"Image too small. Minimum size: {MIN_IMAGE_DIMENSION}x{MIN_IMAGE_DIMENSION}px"
        
        if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
            return False, f"Image too large. Maximum size: {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}px"
        
        return True, None
        
    except Exception as e:
        return False, f"Invalid image file: {str(e)}"


# ============================================
# FILE VALIDATION (CSV/Excel)
# ============================================

ALLOWED_DATA_EXTENSIONS = {'csv', 'xlsx', 'xls'}
MAX_DATA_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def validate_data_file(file):
    """
    Validate CSV/Excel file for import.
    
    Args:
        file: FileStorage object from Flask request
        
    Returns:
        tuple: (is_valid, filename or error_message)
    """
    if not file or not file.filename:
        return False, "No file provided"
    
    filename = secure_filename(file.filename)
    
    if '.' not in filename:
        return False, "File must have an extension"
    
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_DATA_EXTENSIONS:
        return False, f"Invalid file type. Allowed: {', '.join(ALLOWED_DATA_EXTENSIONS)}"
    
    # Check file size
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    
    if size > MAX_DATA_FILE_SIZE:
        return False, f"File too large. Maximum size: {MAX_DATA_FILE_SIZE // (1024*1024)}MB"
    
    if size == 0:
        return False, "File is empty"
    
    return True, filename


# ============================================
# TEXT INPUT VALIDATION
# ============================================

def validate_text_length(text, min_length=0, max_length=None, field_name="Field"):
    """
    Validate text length.
    
    Args:
        text (str): Text to validate
        min_length (int): Minimum length
        max_length (int): Maximum length
        field_name (str): Name of field for error messages
        
    Returns:
        tuple: (is_valid, error_message or None)
    """
    if not text or not text.strip():
        if min_length > 0:
            return False, f"{field_name} is required"
        return True, None
    
    length = len(text.strip())
    
    if length < min_length:
        return False, f"{field_name} must be at least {min_length} characters"
    
    if max_length and length > max_length:
        return False, f"{field_name} must not exceed {max_length} characters"
    
    return True, None


def sanitize_search_query(query, max_length=100):
    """
    Sanitize search query to prevent DoS attacks.
    
    Args:
        query (str): Search query
        max_length (int): Maximum allowed length
        
    Returns:
        str: Sanitized query
    """
    if not query:
        return ""
    
    # Remove extra whitespace
    sanitized = ' '.join(query.strip().split())
    
    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized


# ============================================
# USERNAME VALIDATION
# ============================================

def validate_username(username):
    """
    Validate username format.
    
    Rules:
    - 3-80 characters
    - Alphanumeric, underscore, dash only
    - Must start with letter or number
    
    Args:
        username (str): Username to validate
        
    Returns:
        tuple: (is_valid, error_message or None)
    """
    if not username:
        return False, "Username is required"
    
    if len(username) < 3:
        return False, "Username must be at least 3 characters"
    
    if len(username) > 80:
        return False, "Username must not exceed 80 characters"
    
    # Must start with alphanumeric
    if not username[0].isalnum():
        return False, "Username must start with a letter or number"
    
    # Only alphanumeric, underscore, dash
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return False, "Username can only contain letters, numbers, underscore, and dash"
    
    return True, None
