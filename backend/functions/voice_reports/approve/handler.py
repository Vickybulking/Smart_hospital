import json
import os
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from auth import user_sub, is_group, response


def handler(event, context):
    """Doctor approves (or rejects) a reviewed voice report.

    Only the owning doctor or an admin may decide, and only reports in
    'review' status can be decided. Approval makes the report visible to
    the patient.
    """
    try:
        caller = user_sub(event)
        if not caller:
            return response(401, {'error': 'Authentication required'})

        table_name = os.environ.get('VOICE_REPORTS_TABLE')
        if not table_name:
            raise EnvironmentError('VOICE_REPORTS_TABLE environment variable is not set')

        report_id = (event.get('pathParameters') or {}).get('reportId')
        if not report_id:
            return response(400, {'error': 'reportId path parameter is required'})

        try:
            body = json.loads(event.get('body') or '{}')
        except json.JSONDecodeError:
            body = {}
        decision = body.get('decision')
        if decision not in ('approved', 'rejected'):
            return response(400, {'error': "decision must be 'approved' or 'rejected'"})

        table = boto3.resource('dynamodb').Table(table_name)
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        try:
            result = table.update_item(
                Key={'reportId': report_id},
                UpdateExpression='SET #s = :status, approvedBy = :caller, approvedAt = :now, updatedAt = :now',
                ConditionExpression='attribute_exists(reportId) AND #s = :review AND (doctorId = :caller OR :is_admin = :true)',
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={
                    ':status': decision, ':review': 'review', ':caller': caller,
                    ':is_admin': is_group(event, 'admin'), ':true': True, ':now': now,
                },
                ReturnValues='ALL_NEW',
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                return response(409, {'error': 'Report not found, already decided, or not yours to decide'})
            raise

        return response(200, {'reportId': report_id, 'status': decision,
                              'message': f'Voice report {decision}'})

    except EnvironmentError as e:
        return response(500, {'error': str(e)})
    except Exception as e:
        print(f'Unexpected error approving voice report: {e}')
        return response(500, {'error': 'Internal server error'})
