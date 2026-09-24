# Error handling for Smart Hospital Management System

class ValidationError(Exception):
    """Raised when validation fails"""
    pass

class NotFoundError(Exception):
    """Raised when resource not found"""
    pass

class AuthorizationError(Exception):
    """Raised when authorization fails"""
    pass
