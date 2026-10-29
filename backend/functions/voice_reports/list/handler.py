import json
import os
import sys

import boto3
from boto3.dynamodb.conditions import Attr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from auth import user_sub, is_group, response


def handler(event, context):
    """List voice reports, role-scoped.

    Doctors see the reports they created; patients see their own approved
    reports only; admins see everything.
    """
    try:
        caller = user_sub(event)
        if not caller:
            return response(401, {'error': 'Authentication required'})

        table_name = os.environ.get('VOICE_REPORTS_TABLE')
        if not table_name:
            raise EnvironmentError('VOICE_REPORTS_TABLE environment variable is not set')

        query = event.get('queryStringParameters') or {}
        limit = int(query.get('limit', 50))

        scan = {'Limit': limit}
        filters = None
        if is_group(event, 'patient'):
            filters = Attr('patientId').eq(caller) & Attr('status').eq('approved')
        elif is_group(event, 'doctor'):
            filters = Attr('doctorId').eq(caller)
            patient_id = query.get('patientId')
            if patient_id:
                filters = filters & Attr('patientId').eq(patient_id)
        elif is_group(event, 'admin'):
            patient_id = query.get('patientId')
            if patient_id:
                filters = Attr('patientId').eq(patient_id)
        else:
            return response(403, {'error': 'Not authorised to list voice reports'})

        if filters is not None:
            scan['FilterExpression'] = filters

        result = boto3.resource('dynamodb').Table(table_name).scan(**scan)
        reports = result.get('Items', [])
        body = {'reports': reports, 'count': len(reports)}
        if 'LastEvaluatedKey' in result:
            body['lastKey'] = result['LastEvaluatedKey'].get('reportId')
        return response(200, body)

    except EnvironmentError as e:
        return response(500, {'error': str(e)})
    except Exception as e:
        print(f'Unexpected error listing voice reports: {e}')
        return response(500, {'error': 'Internal server error'})
