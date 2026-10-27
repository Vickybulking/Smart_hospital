#!/usr/bin/env python3
"""Local development server for Carely — runs WITHOUT AWS.

Serves the SAME API contract as the deployed API Gateway, but invokes the
REAL Lambda handler code from backend/functions/* against a moto-emulated
DynamoDB (transactions enforced). Authentication is a mocked JWT: the
frontend's local-mode shim sends a structurally-valid token and this server
decodes its claims the way API Gateway's Cognito authorizer would.

Usage:
    .venv/bin/python scripts/local_dev_server.py          # API on :5111
    python3 -m http.server 8080 --directory frontend      # in another shell

Requires frontend/config.js with localMode: true (see frontend/config.example.js).
"""

import base64
import importlib.util
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import boto3
from moto import mock_aws
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'backend', 'shared'))

PORT = int(os.getenv('PORT', '5111'))

TABLES = {
    'PATIENTS_TABLE': 'local-patients',
    'DOCTORS_TABLE': 'local-doctors',
    'APPOINTMENTS_TABLE': 'local-appointments',
    'APPOINTMENT_SLOTS_TABLE': 'local-slots',
    'MEDICAL_RECORDS_TABLE': 'local-records',
    'DOCUMENTS_TABLE': 'local-documents',
    'DOCUMENTS_BUCKET': 'local-documents-bucket',
    'NOTIFICATIONS_TOPIC_ARN': '',  # skip SNS publish locally
}

LOCAL_BUCKET = 'local-documents-bucket'

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}

_modules = {}
_dispatch_lock = threading.Lock()
s3_client = None  # created in main() after local credentials are configured


def load_handler(*path):
    name = 'local_' + '_'.join(path[1:])
    if name not in _modules:
        file_path = os.path.join(ROOT, *path, 'handler.py')
        spec = importlib.util.spec_from_file_location(name, file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        _modules[name] = module
    return _modules[name]


FNS = 'backend', 'functions'


def jwt_claims(auth_header):
    """Decode the Bearer token payload (no signature check — local only)."""
    if not auth_header or not auth_header.startswith('Bearer '):
        return {}
    token = auth_header[len('Bearer '):].strip()
    try:
        payload_b64 = token.split('.')[1]
        payload_b64 += '=' * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return {}


ROUTES = [
    ('GET',    r'^/doctors$',                     lambda m, q: load_handler(*FNS, 'doctors', 'list')),
    ('POST',   r'^/doctors$',                     lambda m, q: load_handler(*FNS, 'doctors', 'create')),
    ('GET',    r'^/doctors/([^/]+)$',             lambda m, q: load_handler(*FNS, 'doctors', 'get')),
    ('PUT',    r'^/doctors/([^/]+)$',             lambda m, q: load_handler(*FNS, 'doctors', 'update')),
    ('GET',    r'^/doctors/([^/]+)/availability$', lambda m, q: load_handler(*FNS, 'doctors', 'availability', 'get')),
    ('PUT',    r'^/doctors/([^/]+)/availability$', lambda m, q: load_handler(*FNS, 'doctors', 'availability', 'set')),
    ('GET',    r'^/appointments$',                lambda m, q: load_handler(*FNS, 'appointments', 'list')),
    ('POST',   r'^/appointments$',                lambda m, q: load_handler(*FNS, 'appointments', 'create')),
    ('GET',    r'^/appointments/([^/]+)$',        lambda m, q: load_handler(*FNS, 'appointments', 'get')),
    ('DELETE', r'^/appointments/([^/]+)$',        lambda m, q: load_handler(*FNS, 'appointments', 'cancel')),
    ('PUT',    r'^/appointments/([^/]+)/approval$', lambda m, q: load_handler(*FNS, 'appointments', 'approve')),
    ('PUT',    r'^/appointments/([^/]+)/reschedule$', lambda m, q: load_handler(*FNS, 'appointments', 'reschedule')),
    ('GET',    r'^/patients$',                    lambda m, q: load_handler(*FNS, 'patients', 'list')),
    ('POST',   r'^/patients$',                    lambda m, q: load_handler(*FNS, 'patients', 'create')),
    ('GET',    r'^/patients/([^/]+)$',            lambda m, q: load_handler(*FNS, 'patients', 'get')),
    ('PUT',    r'^/patients/([^/]+)$',            lambda m, q: load_handler(*FNS, 'patients', 'update')),
    ('GET',    r'^/medical-records$',             lambda m, q: load_handler(*FNS, 'medical_records', 'list')),
    ('POST',   r'^/medical-records$',             lambda m, q: load_handler(*FNS, 'medical_records', 'create')),
    ('GET',    r'^/medical-records/([^/]+)$',     lambda m, q: load_handler(*FNS, 'medical_records', 'get')),
    ('GET',    r'^/documents$',                   lambda m, q: load_handler(*FNS, 'documents', 'list')),
    ('POST',   r'^/documents/upload-url$',        lambda m, q: load_handler(*FNS, 'documents', 'generate_upload_url')),
    ('GET',    r'^/documents/download-url$',      lambda m, q: load_handler(*FNS, 'documents', 'generate_download_url')),
    ('POST',   r'^/documents/metadata$',          lambda m, q: load_handler(*FNS, 'documents', 'save_metadata')),
    ('DELETE', r'^/documents/([^/]+)$',           lambda m, q: load_handler(*FNS, 'documents', 'delete')),
]


# route param names, parallel to the regexes above
PARAM_NAME = {
    '/doctors/([^/]+)': 'doctorId',
    '/doctors/([^/]+)/availability': 'doctorId',
    '/appointments/([^/]+)': 'appointmentId',
    '/appointments/([^/]+)/approval': 'appointmentId',
    '/appointments/([^/]+)/reschedule': 'appointmentId',
    '/patients/([^/]+)': 'patientId',
    '/medical-records/([^/]+)': 'recordId',
    '/documents/([^/]+)': 'documentId',
}


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')

    def _read_raw(self):
        length = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(length) if length else b''

    def _send_json(self, status, payload):
        msg = json.dumps(payload)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.send_header('Content-Length', str(len(msg.encode())))
        self.end_headers()
        self.wfile.write(msg.encode())

    def _handle(self, method):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query) if parsed.query else {}

        if method == 'OPTIONS':
            self.send_response(204)
            self._cors()
            self.end_headers()
            return

        # Local byte-transfer endpoints: moto's presigned URLs are not
        # reachable from a browser, so local mode uploads/downloads the raw
        # object through this server instead. The API contract (upload-url,
        # metadata, download-url, list) is unchanged.
        claims = jwt_claims(self.headers.get('Authorization'))
        if parsed.path == '/local-upload' and method == 'PUT':
            file_key = (query.get('fileKey') or [''])[0]
            caller = claims.get('sub', '')
            if not caller or not file_key.startswith(f'documents/{caller}/'):
                self._send_json(403, {'error': 'Not authorised to upload this file key'})
                return
            length = int(self.headers.get('Content-Length') or 0)
            raw = self.rfile.read(length)
            with _dispatch_lock:
                s3_client.put_object(
                    Bucket=LOCAL_BUCKET, Key=file_key, Body=raw,
                    ContentType=self.headers.get('Content-Type', 'application/octet-stream'))
            self._send_json(200, {'status': 'success', 'fileKey': file_key, 'bytes': len(raw)})
            print(f'{"PUT":7} /local-upload -> 200  ({claims.get("email", "?")}, {len(raw)} bytes)')
            return
        if parsed.path == '/local-download' and method == 'GET':
            file_key = (query.get('fileKey') or [''])[0]
            caller = claims.get('sub', '')
            if not caller or (
                not file_key.startswith(f'documents/{caller}/')
                and 'doctor' not in claims.get('cognito:groups', [])
                and 'admin' not in claims.get('cognito:groups', [])
            ):
                self._send_json(403, {'error': 'Not authorised to download this file key'})
                return
            with _dispatch_lock:
                try:
                    obj = s3_client.get_object(Bucket=LOCAL_BUCKET, Key=file_key)
                    raw = obj['Body'].read()
                    ctype = obj.get('ContentType', 'application/octet-stream')
                except s3_client.exceptions.NoSuchKey:
                    self._send_json(404, {'error': f'{file_key} not found'})
                    return
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Disposition', f'attachment; filename="{file_key.rsplit("/", 1)[-1]}"')
            self._cors()
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            print(f'{"GET":7} /local-download -> 200  ({claims.get("email", "?")}, {len(raw)} bytes)')
            return

        body = self._read_raw().decode('utf-8', errors='replace') if method in ('POST', 'PUT') else None

        for route_method, pattern, loader in ROUTES:
            if route_method != method:
                continue
            match = re.match(pattern, parsed.path)
            if not match:
                continue

            claims = jwt_claims(self.headers.get('Authorization'))

            # rebuild pathParameters with the correct key name for this route
            param_key = None
            for frag, name in PARAM_NAME.items():
                if frag in pattern:
                    param_key = name
                    break

            event = {
                'httpMethod': method,
                'body': body,
                'queryStringParameters': {k: v[-1] for k, v in query.items()} or None,
                'requestContext': {'authorizer': {'claims': claims}},
            }
            if match.groups():
                event['pathParameters'] = {param_key or 'id': match.group(1)}

            handler_module = loader(match, query)
            with _dispatch_lock:  # moto backends are not thread-safe
                try:
                    result = handler_module.handler(event, None)
                except Exception as e:
                    print(f'  !! handler crashed: {e}')
                    result = {'statusCode': 500, 'headers': {},
                              'body': json.dumps({'error': f'handler error: {e}'})}

            status = result.get('statusCode', 200)
            resp_body = result.get('body', '')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.send_header('Content-Length', str(len(resp_body.encode())))
            self.end_headers()
            self.wfile.write(resp_body.encode())
            print(f'{method:7} {parsed.path:45} -> {status}  ({claims.get("email", "anonymous")})')
            return

        self.send_response(404)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        msg = json.dumps({'error': f'No local route for {method} {parsed.path}'})
        self.send_header('Content-Length', str(len(msg.encode())))
        self.end_headers()
        self.wfile.write(msg.encode())

    def do_GET(self): self._handle('GET')
    def do_POST(self): self._handle('POST')
    def do_PUT(self): self._handle('PUT')
    def do_DELETE(self): self._handle('DELETE')
    def do_OPTIONS(self): self._handle('OPTIONS')

    def log_message(self, *a):  # silence default noisy logging; we print our own
        pass


def call(handler_module, event):
    return handler_module.handler(event, None)


def seed():
    """Seed demo data THROUGH the real handlers (extra verification for free)."""
    def event(body, sub, groups, method='POST', path=None):
        e = {'httpMethod': method,
             'body': json.dumps(body) if body is not None else None,
             'requestContext': {'authorizer': {'claims': {'sub': sub, 'cognito:groups': groups}}}}
        if path:
            e['pathParameters'] = path
        return e

    doctor_sub = 'local-doctor-1'
    print('Seeding via real handlers…')
    r = call(load_handler(*FNS, 'doctors', 'create'), event(
        {'name': 'Dr. Maya Patel', 'email': 'maya@local.test', 'specialty': 'Cardiology',
         'qualification': 'MBBS, MD', 'experience': '12 years'}, doctor_sub, ['doctor']))
    assert r['statusCode'] == 201, r['body']

    avail = {day: ['09:00', '10:30', '14:00'] for day in
             ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']}
    r = call(load_handler(*FNS, 'doctors', 'availability', 'set'), event(
        {'availability': avail}, doctor_sub, ['doctor'], method='PUT', path={'doctorId': doctor_sub}))
    assert r['statusCode'] == 200, r['body']

    for sub, name, email in [('local-patient-1', 'Priya Sharma', 'priya@local.test'),
                             ('local-patient-2', 'Rahul Mehta', 'rahul@local.test')]:
        r = call(load_handler(*FNS, 'patients', 'create'), event(
            {'name': name, 'email': email, 'phone': '+91 90000 00000',
             'bloodGroup': 'O+'}, sub, ['patient']))
        assert r['statusCode'] == 201, r['body']

    print('Seeded: 1 doctor (7-day availability), 2 patients\n')


def main():
    os.environ.update(TABLES)
    os.environ.setdefault('AWS_DEFAULT_REGION', 'ap-south-1')
    os.environ.setdefault('AWS_ACCESS_KEY_ID', 'local')
    os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'local')

    mock = mock_aws()
    mock.start()
    global s3_client
    s3_client = boto3.client('s3')
    dynamo = boto3.resource('dynamodb')
    for name, key in [('local-patients', 'patientId'), ('local-doctors', 'doctorId'),
                      ('local-appointments', 'appointmentId'), ('local-slots', 'slotKey'),
                      ('local-records', 'recordId'), ('local-documents', 'documentId')]:
        dynamo.create_table(
            TableName=name,
            KeySchema=[{'AttributeName': key, 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': key, 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST',
        )
    region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
    if region == 'us-east-1':
        s3_client.create_bucket(Bucket=LOCAL_BUCKET)
    else:
        s3_client.create_bucket(
            Bucket=LOCAL_BUCKET,
            CreateBucketConfiguration={'LocationConstraint': region},
        )

    seed()

    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print(f'Carely LOCAL dev API on http://127.0.0.1:{PORT} (real handlers + moto DynamoDB)')
    print('Serve the frontend with:  python3 -m http.server 8080 --directory frontend\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down.')


if __name__ == '__main__':
    main()
