import json
import boto3

def handler(event, context):
    """Get a doctor by ID"""
    try:
        doctor_id = event.get('pathParameters', {}).get('doctorId')
        if not doctor_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'doctorId path parameter is required'})
            }
        
        # Mock response
        doctor = {
            'doctorId': doctor_id,
            'name': 'Dr. Smith',
            'email': 'dr.smith@example.com',
            'specialty': 'Cardiology',
            'availability': 'Available',
            'role': 'doctor'
        }
        
        return {
            'statusCode': 200,
            'body': json.dumps(doctor)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
