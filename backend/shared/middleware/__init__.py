# Middleware for Smart Hospital Management System

class AuthMiddleware:
    """Authentication middleware for Lambda functions"""
    
    def __init__(self):
        pass
    
    def verify(self, event):
        """Verify Cognito token"""
        # In real implementation, verify the JWT token
        return {'valid': True, 'user': {'role': 'patient'}}
