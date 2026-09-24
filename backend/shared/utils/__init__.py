# Utility functions for Smart Hospital Management System

import json
import uuid
from datetime import datetime

def generate_id():
    """Generate a unique ID"""
    return str(uuid.uuid4())

def current_time():
    """Get current UTC time as ISO string"""
    return datetime.utcnow().isoformat() + 'Z'
