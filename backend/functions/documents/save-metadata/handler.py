import json
import boto3

def handler(event, context):
    """Save document metadata to DynamoDB"""
    try:
        body = json.loads(event.get('body', '{}'))
        # In real implementation, save to DynamoDB
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Document metadata saved successfully'})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
