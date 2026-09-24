import json
import sys
import os

# Add shared utilities to path
sys.path.insert(0, os.path.dirname(__file__))

def handler(event, context):
    """Main Lambda handler"""
    print('Received event:', json.dumps(event))
    
    # Basic routing based on path
    path = event.get('rawPath', event.get('path', ''))
    http_method = event.get('rawMethod', event.get('httpMethod', 'GET'))
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': f'{http_method} {path}',
            'event': event
        })
    }
