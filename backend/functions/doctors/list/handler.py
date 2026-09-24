import json
import boto3

def handler(event, context):
    """List all doctors"""
    try:
        # Mock response
        doctors = [
            {'doctorId': '1', 'name': 'Dr. Smith', 'specialty': 'Cardiology', 'availability': 'Available'},
            {'doctorId': '2', 'name': 'Dr. Johnson', 'specialty': 'Neurology', 'availability': 'Available'}
        ]
        
        return {
            'statusCode': 200,
            'body': json.dumps(doctors)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
