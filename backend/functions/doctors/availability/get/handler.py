import json
import os

import boto3

dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def handler(event, context):
    """
    Get a doctor's availability schedule from DynamoDB.

    The availability is stored directly on the doctor record as a structured attribute:

        availability: {
            "monday":    ["09:00", "10:00", "14:00"],
            "tuesday":   ["09:00", "11:00"],
            ...
            "saturday":  [],
            "sunday":    []
        }

    Returns the raw availability map plus a flattened list of available slots.
    """
    try:
        doctor_id = (event.get('pathParameters') or {}).get('doctorId')
        if not doctor_id:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'doctorId path parameter is required'}),
            }

        table_name = os.environ.get('DOCTORS_TABLE')
        if not table_name:
            raise EnvironmentError('DOCTORS_TABLE environment variable is not set')

        table = dynamodb.Table(table_name)
        # Only project the fields we need — cheaper read
        response = table.get_item(
            Key={'doctorId': doctor_id},
            ProjectionExpression='doctorId, #nm, availability',
            ExpressionAttributeNames={'#nm': 'name'},
        )

        item = response.get('Item')
        if not item:
            return {
                'statusCode': 404,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': f'Doctor {doctor_id} not found'}),
            }

        availability = item.get('availability', {})

        # Build a flat list of {day, time} slots for convenience
        slots = [
            {'day': day, 'time': time}
            for day, times in availability.items()
            for time in (times if isinstance(times, list) else [])
        ]

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'doctorId': doctor_id,
                'doctorName': item.get('name', ''),
                'availability': availability,
                'slots': slots,
                'totalSlots': len(slots),
            }),
        }

    except EnvironmentError as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)}),
        }
    except Exception as e:
        print(f'Unexpected error fetching availability for doctor {doctor_id}: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
