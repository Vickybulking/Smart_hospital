#!/usr/bin/env python3
"""Carely local speech-to-text service — whisper.cpp (open source, offline).

The doctor portal records consultation audio in the browser and POSTs it here;
this service transcribes it locally with whisper.cpp (OpenAI Whisper models,
GGML format) and returns timestamped segments. No AWS, no internet required.

Usage:
    python3 scripts/whisper_server.py [--model models/ggml-small.en.bin] [--port 5200]

Endpoints:
    GET  /health                 -> {status, model, engine}
    POST /transcribe             -> raw audio bytes in the request body
                                    (any format ffmpeg reads: wav, webm, mp3, m4a)
                                    query: ?language=en  (default en)
                                    response: {text, segments: [{start, end, text}], duration}
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
}

WHISPER_CLI = shutil.which('whisper-cli') or '/opt/homebrew/bin/whisper-cli'
FFMPEG = shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
MODEL_PATH = ''
ENGINE = 'whisper.cpp (OpenAI Whisper, GGML)'

SEGMENT_RE = re.compile(r'\[(\d+):(\d+):(\d+\.\d+)\s*-->\s*(\d+):(\d+):(\d+\.\d+)\]\s*(.*)')


def to_ms(h, m, s):
    return (int(h) * 3600 + int(m) * 60 + float(s)) * 1000


def transcribe_file(input_path: str, language: str):
    """Convert input to 16 kHz mono WAV, run whisper-cli, parse segments."""
    tmpdir = tempfile.mkdtemp(prefix='carely-whisper-')
    try:
        wav_path = os.path.join(tmpdir, 'input16.wav')
        subprocess.run(
            [FFMPEG, '-y', '-i', input_path, '-ar', '16000', '-ac', '1',
             '-c:a', 'pcm_s16le', wav_path],
            check=True, capture_output=True)

        out_prefix = os.path.join(tmpdir, 'transcript')
        cmd = [WHISPER_CLI, '-m', MODEL_PATH, '-f', wav_path,
               '-oj', '-of', out_prefix, '-l', language]
        started = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        elapsed = round(time.time() - started, 2)
        if proc.returncode != 0:
            raise RuntimeError(f'whisper-cli failed: {proc.stderr[-400:]}')

        json_path = out_prefix + '.json'
        segments, full_text, language_detected = [], [], language
        if os.path.exists(json_path):
            with open(json_path) as f:
                result = json.load(f)
            language_detected = result.get('result', {}).get('language', language)
            for tr in result.get('transcription', []):
                text = (tr.get('text') or '').strip()
                if not text:
                    continue
                ts = tr.get('timestamps', {})
                t_from, t_to = ts.get('from', ''), ts.get('to', '')

                def ms(stamp):
                    m = re.match(r'(\d+):(\d+):(\d+\.\d+)', stamp or '')
                    return to_ms(*m.groups()) if m else 0
                segments.append({'start': t_from, 'end': t_to,
                                 'start_ms': ms(t_from), 'end_ms': ms(t_to), 'text': text})
                full_text.append(text)
        else:  # fall back to parsing stdout
            for line in proc.stdout.splitlines():
                m = SEGMENT_RE.search(line)
                if m and m.group(7).strip():
                    segments.append({'start': f'{m.group(1)}:{m.group(2)}:{m.group(3)}',
                                     'end': f'{m.group(4)}:{m.group(5)}:{m.group(6)}',
                                     'text': m.group(7).strip()})
                    full_text.append(m.group(7).strip())

        return {'text': ' '.join(full_text), 'segments': segments,
                'language': language_detected, 'transcription_seconds': elapsed}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def _cors(self):
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        if urlparse(self.path).path == '/health':
            self._json(200, {'status': 'ok', 'engine': ENGINE,
                             'model': os.path.basename(MODEL_PATH),
                             'model_exists': os.path.exists(MODEL_PATH)})
        else:
            self._json(404, {'error': 'not found'})

    def do_POST(self):
        path = urlparse(self.path).path
        if path != '/transcribe':
            return self._json(404, {'error': 'not found'})
        if not os.path.exists(MODEL_PATH):
            return self._json(503, {'error': f'model not found at {MODEL_PATH}'})

        length = int(self.headers.get('Content-Length') or 0)
        if length == 0:
            return self._json(400, {'error': 'empty request body — send raw audio bytes'})
        audio = self.rfile.read(length)

        ctype = (self.headers.get('Content-Type') or 'audio/webm').split(';')[0].strip().lower()
        ext = {'audio/webm': '.webm', 'audio/ogg': '.ogg', 'audio/mpeg': '.mp3',
               'audio/mp4': '.m4a', 'audio/x-m4a': '.m4a', 'audio/wav': '.wav',
               'audio/x-wav': '.wav'}.get(ctype, '.webm')

        query = parse_qs(urlparse(self.path).query)
        language = (query.get('language') or ['en'])[0]

        tmpdir = tempfile.mkdtemp(prefix='carely-upload-')
        try:
            input_path = os.path.join(tmpdir, 'audio' + ext)
            with open(input_path, 'wb') as f:
                f.write(audio)
            started = time.time()
            result = transcribe_file(input_path, language)
            result['total_seconds'] = round(time.time() - started, 2)
            self._json(200, result)
            print(f'/transcribe: {length} bytes ({ctype}) -> {len(result["text"])} chars '
                  f'in {result["total_seconds"]}s')
        except subprocess.CalledProcessError as e:
            self._json(415, {'error': 'unsupported audio format', 'detail': e.stderr[-200:] if e.stderr else ''})
        except Exception as e:
            self._json(500, {'error': str(e)})
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def log_message(self, *a):
        pass


def main():
    global MODEL_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default=os.path.join(
        os.path.dirname(__file__), '..', 'models', 'ggml-small.en.bin'))
    parser.add_argument('--port', type=int, default=5200)
    args = parser.parse_args()
    MODEL_PATH = os.path.abspath(args.model)

    if not os.path.exists(WHISPER_CLI):
        raise SystemExit(f'whisper-cli not found at {WHISPER_CLI} — run: brew install whisper-cpp')
    if not os.path.exists(MODEL_PATH):
        raise SystemExit(f'model not found at {MODEL_PATH} — download ggml-small.en.bin first')

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Carely Whisper STT service on http://127.0.0.1:{args.port}')
    print(f'  engine: {ENGINE}')
    print(f'  model:  {MODEL_PATH}')
    print(f'  POST /transcribe with raw audio bytes; GET /health')
    server.serve_forever()


if __name__ == '__main__':
    main()
