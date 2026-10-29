import json
import os
import sys
import uuid

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from auth import user_sub, is_group, response

s3 = boto3.client('s3')

EXT_MAP = {
    'audio/webm': '.webm', 'audio/ogg': '.ogg', 'audio/wav': '.wav',
    'audio/x-wav': '.wav', 'audio/mpeg': '.mp3', 'audio/mp4': '.m4a',
    'audio/x-m4a': '.m4a',
}


def handler(event, context):
    """Presigned PUT URL for the doctor's consultation audio.

    Audio is stored under audio/<doctorSub>/ so a doctor can only write
    into their own prefix.
    """
    try:
        caller = user_sub(event)
        if not caller or not is_group(event, 'doctor'):
            return response(403, {'error': 'Only authenticated doctors can upload consultation audio'})

        bucket = os.environ.get('DOCUMENTS_BUCKET')
        if not bucket:
            raise EnvironmentError('DOCUMENTS_BUCKET environment variable is not set')

        try:
            body = json.loads(event.get('body') or '{}')
        except json.JSONDecodeError:
            body = {}
        content_type = body.get('contentType', 'audio/webm')
        ext = EXT_MAP.get(content_type.split(';')[0].strip().lower(), '.webm')

        file_key = f'audio/{caller}/{uuid.uuid4().hex}{ext}'
        url = s3.generate_presigned_url(
            'put_object',
            Params={'Bucket': bucket, 'Key': file_key, 'ContentType': content_type},
            ExpiresIn=3600)
        return response(200, {'uploadUrl': url, 'fileKey': file_key, 'contentType': content_type})

    except EnvironmentError as e:
        return response(500, {'error': str(e)})
    except Exception as e:
        print(f'Unexpected error generating voice upload URL: {e}')
        return response(500, {'error': 'Internal server error'})
