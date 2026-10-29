import json
import os
import sys
import uuid
from datetime import datetime, timezone

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from auth import user_sub, is_group, response
from medical_extract import extract_with_fallback

s3 = boto3.client('s3')
transcribe = boto3.client('transcribe')
bedrock = boto3.client('bedrock-runtime')


def handler(event, context):
    """Create a voice report.

    Two modes:
    1. {audioKey}        — audio already in S3 (presigned upload): starts an
                            Amazon Transcribe job with speaker labels.
    2. {transcript}      — a ready dialogue (e.g. from live browser
                            speech-to-text): runs extraction immediately.
    Doctors only.
    """
    try:
        caller = user_sub(event)
        if not caller or not is_group(event, 'doctor'):
            return response(403, {'error': 'Only authenticated doctors can create voice reports'})

        bucket = os.environ.get('DOCUMENTS_BUCKET')
        table_name = os.environ.get('VOICE_REPORTS_TABLE')
        language = os.environ.get('TRANSCRIBE_LANGUAGE', 'en-IN')
        model_id = os.environ.get('BEDROCK_MODEL_ID', 'apac.amazon.nova-lite-v1:0')
        if not bucket or not table_name:
            raise EnvironmentError('VOICE_REPORTS_TABLE / DOCUMENTS_BUCKET not configured')

        try:
            body = json.loads(event.get('body') or '{}')
        except json.JSONDecodeError:
            body = {}

        patient_id = (body.get('patientId') or '').strip()
        audio_key = (body.get('audioKey') or '').strip()
        transcript = (body.get('transcript') or '').strip()
        audio_name = (body.get('audioFileName') or 'consultation-recording').strip()
        if not patient_id or not (audio_key or transcript):
            return response(400, {'error': 'patientId and (audioKey or transcript) are required'})
        if audio_key and not audio_key.startswith(f'audio/{caller}/'):
            return response(403, {'error': 'Doctors may only transcribe their own uploaded audio'})

        report_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')

        if transcript:
            # Browser speech-to-text mode — extract immediately.
            try:
                structured, method = extract_with_fallback(bedrock, model_id, transcript)
                status = 'review'
                error_message = ''
            except Exception as ext_err:
                structured, method, status = None, 'none', 'error'
                error_message = f'Extraction failed: {ext_err}'
            report = {
                'reportId': report_id, 'doctorId': caller, 'patientId': patient_id,
                'audioKey': '', 'audioFileName': audio_name or 'Live dictation',
                'jobName': '', 'status': status, 'transcript': transcript,
                'structured': structured, 'extractionMethod': method,
                'errorMessage': error_message, 'createdAt': now, 'updatedAt': now, 'approvedAt': '',
            }
            boto3.resource('dynamodb').Table(table_name).put_item(Item=report)
            return response(201, {'reportId': report_id, 'status': status,
                                  'extractionMethod': method,
                                  'message': 'Voice report created with transcript'})

        # Audio mode — start Transcribe.
        job_name = f'carely-{report_id}'
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            LanguageCode=language,
            Media={'MediaFileUri': f's3://{bucket}/{audio_key}'},
            OutputBucketName=bucket,
            OutputKey=f'transcribe/{report_id}.json',
            Settings={'ShowSpeakerLabels': True, 'MaxSpeakerLabels': 2},
        )
        report = {
            'reportId': report_id, 'doctorId': caller, 'patientId': patient_id,
            'audioKey': audio_key, 'audioFileName': audio_name, 'jobName': job_name,
            'status': 'transcribing', 'transcript': '', 'structured': None,
            'extractionMethod': '', 'errorMessage': '', 'createdAt': now,
            'updatedAt': now, 'approvedAt': '',
        }
        boto3.resource('dynamodb').Table(table_name).put_item(Item=report)
        return response(201, {'reportId': report_id, 'status': 'transcribing',
                              'message': 'Voice report created — Transcribe job started'})

    except transcribe.exceptions.BadRequestException as e:
        return response(400, {'error': f'Transcribe rejected the audio: {str(e)}'})
    except EnvironmentError as e:
        return response(500, {'error': str(e)})
    except Exception as e:
        print(f'Unexpected error creating voice report: {e}')
        return response(500, {'error': 'Internal server error'})
