# Validators for Smart Hospital Management System

def validate_patient_data(data):
    """Validate patient data"""
    errors = []
    if not data.get('name'):
        errors.append('Name is required')
    if not data.get('email'):
        errors.append('Email is required')
    if not '@' in data.get('email', ''):
        errors.append('Valid email is required')
    return errors

def validate_appointment_data(data):
    """Validate appointment data"""
    errors = []
    if not data.get('patientId'):
        errors.append('patientId is required')
    if not data.get('doctorId'):
        errors.append('doctorId is required')
    if not data.get('dateTime'):
        errors.append('dateTime is required')
    return errors
