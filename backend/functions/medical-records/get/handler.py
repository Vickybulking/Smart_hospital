import json
import boto3

def handler(event, context):
    """Get a medical record by ID"""
    try:
        record_id = event.get('pathParameters', {}).get('recordId')
        if not record_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'recordId path parameter is required'})
            }
        
        # Mock response
        record = {
            'recordId': record_id,
            'patientId': '1',
            'doctorId': '1',
            'title': 'Patient Consultation Notes',
            'contentUrl': 's3://bucket/path/to/record',
            'createdAt': '2024-01-01T00:00:00Z',
            'updatedAt': '2024-01-01T00:00:00Z'
        }
        
        return {
            'statusCode': 200,
            'body': json.dumps(record)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
