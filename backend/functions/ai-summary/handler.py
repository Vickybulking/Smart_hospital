import json
import os

import boto3
from botocore.exceptions import ClientError

# Bedrock runtime client – region must match where your model access is granted
bedrock = boto3.client('bedrock-runtime', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
dynamodb = boto3.resource('dynamodb')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}

# Model selection: prefer Claude 3 Haiku (fast + cheap) with Titan Text as fallback.
# Set MODEL_ID env var in SAM template to override.
DEFAULT_MODEL_ID = 'anthropic.claude-3-haiku-20240307-v1:0'

SYSTEM_PROMPT = (
    'You are a clinical summarisation assistant integrated into a hospital management system. '
    'Your job is to produce concise, accurate summaries of medical documents and patient records. '
    'Use plain clinical language. Never fabricate diagnoses or treatment recommendations. '
    'If the input is insufficient, say so clearly rather than guessing.'
)


def _build_claude_payload(document_text: str, max_tokens: int = 512) -> dict:
    """Build the request body for Claude 3 (Messages API)."""
    return {
        'anthropic_version': 'bedrock-2023-05-31',
        'max_tokens': max_tokens,
        'system': SYSTEM_PROMPT,
        'messages': [
            {
                'role': 'user',
                'content': (
                    'Please provide a concise clinical summary of the following medical document. '
                    'Include: key findings, diagnoses (if present), medications (if any), '
                    'and any follow-up actions mentioned.\n\n'
                    f'--- DOCUMENT ---\n{document_text}\n--- END ---'
                ),
            }
        ],
    }


def _build_titan_payload(document_text: str, max_tokens: int = 512) -> dict:
    """Build the request body for Amazon Titan Text (fallback model)."""
    prompt = (
        f'{SYSTEM_PROMPT}\n\n'
        'Provide a concise clinical summary of the following medical document. '
        'Include: key findings, diagnoses, medications, and follow-up actions.\n\n'
        f'Document:\n{document_text}\n\nSummary:'
    )
    return {
        'inputText': prompt,
        'textGenerationConfig': {
            'maxTokenCount': max_tokens,
            'temperature': 0.3,
            'topP': 0.9,
        },
    }


def _extract_text(model_id: str, response_body: dict) -> str:
    """Extract the generated text from a Bedrock response based on the model family."""
    if 'claude' in model_id:
        # Claude Messages API: content[0].text
        return response_body.get('content', [{}])[0].get('text', '').strip()
    elif 'titan' in model_id:
        # Titan Text: results[0].outputText
        return response_body.get('results', [{}])[0].get('outputText', '').strip()
    # Generic fallback
    return response_body.get('completion', str(response_body)).strip()


def _invoke_bedrock(model_id: str, payload: dict) -> str:
    """Call Bedrock InvokeModel and return the extracted summary text."""
    response = bedrock.invoke_model(
        modelId=model_id,
        contentType='application/json',
        accept='application/json',
        body=json.dumps(payload),
    )
    response_body = json.loads(response['body'].read())
    return _extract_text(model_id, response_body)


def _fetch_document_text(document_id: str) -> str | None:
    """
    Try to load the document text from DynamoDB metadata.
    If the record has a 'content' field, return it directly.
    If it only has a fileKey, return None (S3 fetch not implemented here —
    callers should pass document_text directly for large files).
    """
    table_name = os.environ.get('DOCUMENTS_TABLE')
    if not table_name or not document_id:
        return None

    table = dynamodb.Table(table_name)
    resp = table.get_item(Key={'documentId': document_id})
    item = resp.get('Item')
    if item:
        return item.get('content') or item.get('description') or None
    return None


def handler(event, context):
    """
    Generate an AI-powered clinical summary using Amazon Bedrock.

    Request body (JSON):
        documentId   – (optional) ID of an existing document in DocumentsTable
        documentText – (optional) Raw text to summarise directly
        maxTokens    – (optional, int) Max output tokens, default 512

    At least one of documentId or documentText must be provided.
    If both are provided, documentText takes precedence.
    """
    try:
        raw_body = event.get('body') or '{}'
        body = json.loads(raw_body)

        document_text = body.get('documentText', '').strip()
        document_id = body.get('documentId', '').strip()
        max_tokens = int(body.get('maxTokens', 512))

        # If no direct text, try to load from DynamoDB
        if not document_text and document_id:
            document_text = _fetch_document_text(document_id) or ''

        if not document_text:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({
                    'error': 'Provide either "documentText" or a valid "documentId" with stored content',
                }),
            }

        model_id = os.environ.get('BEDROCK_MODEL_ID', DEFAULT_MODEL_ID)

        # Build payload based on model family
        if 'claude' in model_id:
            payload = _build_claude_payload(document_text, max_tokens)
        else:
            payload = _build_titan_payload(document_text, max_tokens)

        summary = _invoke_bedrock(model_id, payload)

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'documentId': document_id or None,
                'summary': summary,
                'modelId': model_id,
                'inputChars': len(document_text),
            }),
        }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        print(f'Bedrock ClientError [{error_code}]: {e}')

        # Surface friendly messages for the most common Bedrock errors
        if error_code == 'AccessDeniedException':
            return {
                'statusCode': 403,
                'headers': CORS_HEADERS,
                'body': json.dumps({
                    'error': 'Model access not granted. Enable the model in the Bedrock console first.',
                    'code': error_code,
                }),
            }
        if error_code == 'ValidationException':
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': f'Invalid request to Bedrock: {e}', 'code': error_code}),
            }
        if error_code == 'ThrottlingException':
            return {
                'statusCode': 429,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Bedrock throttled the request — please retry', 'code': error_code}),
            }
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': f'Bedrock error: {error_code}'}),
        }
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Invalid JSON in request body'}),
        }
    except Exception as e:
        print(f'Unexpected error in ai-summary: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal server error'}),
        }
