import json
import boto3

def handler(event, context):
    """List medical records"""
    try:
        # Mock response
        records = [
            {'recordId': '1', 'patientId': '1', 'doctorId': '1', 'title': 'Patient Consultation Notes', 'contentUrl': 's3://bucket/path/to/record'}
        ]
        
        return {
            'statusCode': 200,
            'body': json.dumps(records)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
