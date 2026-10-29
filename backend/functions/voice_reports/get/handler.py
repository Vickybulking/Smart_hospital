import json
import os
import sys
from datetime import datetime, timezone

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from auth import user_sub, is_group, response
from medical_extract import dialogue_from_transcribe, extract_with_fallback

s3 = boto3.client('s3')
transcribe = boto3.client('transcribe')
bedrock = boto3.client('bedrock-runtime')


def _deny(status, message):
    return response(status, {'error': message})


def handler(event, context):
    """Fetch a voice report; while status is 'transcribing', poll the Transcribe
    job and, once the transcript is ready, run Bedrock extraction.

    Access: the owning doctor, any admin, and the patient — but patients
    only see reports once the doctor has approved them.
    """
    try:
        caller = user_sub(event)
        if not caller:
            return _deny(401, 'Authentication required')

        table_name = os.environ.get('VOICE_REPORTS_TABLE')
        bucket = os.environ.get('DOCUMENTS_BUCKET')
        model_id = os.environ.get('BEDROCK_MODEL_ID', 'apac.amazon.nova-lite-v1:0')
        if not table_name or not bucket:
            raise EnvironmentError('VOICE_REPORTS_TABLE / DOCUMENTS_BUCKET not configured')

        report_id = (event.get('pathParameters') or {}).get('reportId')
        if not report_id:
            return _deny(400, 'reportId path parameter is required')

        table = boto3.resource('dynamodb').Table(table_name)
        report = table.get_item(Key={'reportId': report_id}).get('Item')
        if not report:
            return _deny(404, f'Voice report {report_id} not found')

        is_owner_doctor = report.get('doctorId') == caller
        is_patient_owner = report.get('patientId') == caller
        if not (is_owner_doctor or is_patient_owner or is_group(event, 'admin')):
            return _deny(403, 'You are not a participant in this voice report')
        if is_patient_owner and report.get('status') != 'approved':
            return _deny(403, 'This report is not approved for patient viewing yet')

        # ── poll Transcribe while the job runs ──────────────────────────────
        if report.get('status') == 'transcribing' and report.get('jobName'):
            job = transcribe.get_transcription_job(
                TranscriptionJobName=report['jobName'])['TranscriptionJob']
            status = job['TranscriptionJobStatus']

            if status == 'IN_PROGRESS':
                report['transcribeStatus'] = 'IN_PROGRESS'
                return response(200, {'report': report})

            now = datetime.now(timezone.utc).isoformat(timespec='seconds')
            if status == 'FAILED':
                report.update(status='error', errorMessage=job.get('FailureReason', 'Transcription failed'),
                              updatedAt=now)
                table.put_item(Item=report)
                return response(200, {'report': report})

            if status == 'COMPLETED':
                transcript_uri = job['Transcript']['TranscriptFileUri']
                # The transcript JSON lives in our own bucket — read it with S3
                key = transcript_uri.split('.com/', 1)[-1].split('.com/', 1)[-1]
                key = key.split('amazonaws.com/')[-1] if 'amazonaws.com/' in key else key
                obj = s3.get_object(Bucket=bucket, Key=key)
                job_result = json.loads(obj['Body'].read())

                dialogue, _speakers = dialogue_from_transcribe(job_result)
                if not dialogue.strip():
                    report.update(status='error', errorMessage='No speech detected in the recording',
                                  transcript=dialogue, updatedAt=now)
                    table.put_item(Item=report)
                    return response(200, {'report': report})

                try:
                    structured, method = extract_with_fallback(bedrock, model_id, dialogue)
                    report.update(status='review', transcript=dialogue, structured=structured,
                                  extractionMethod=method, errorMessage='', updatedAt=now)
                except Exception as ext_err:
                    print(f'Extraction failed: {ext_err}')
                    report.update(status='error', transcript=dialogue,
                                  errorMessage=f'AI extraction failed: {ext_err}', updatedAt=now)
                table.put_item(Item=report)

        return response(200, {'report': report})

    except EnvironmentError as e:
        return response(500, {'error': str(e)})
    except Exception as e:
        print(f'Unexpected error fetching voice report {locals().get("report_id", "?")}: {e}')
        return response(500, {'error': 'Internal server error'})
