"""Shared Bedrock extraction for voice-to-medical-report.

Turns an Amazon Transcribe output JSON (with speaker labels) into a
speaker-attributed dialogue and asks Bedrock to extract a STRICT verbatim
structure. The extraction prompt is deliberately conservative: it may only
surface what was explicitly spoken and must leave fields empty otherwise —
the AI assists documentation, it never diagnoses.
"""

import json

BEDROCK_SYSTEM_PROMPT = """You are a clinical transcription clerk — a meticulous, impartial record-keeper.
You will receive the raw transcript of a doctor-patient consultation.

Your sole function is VERBATIM EXTRACTION: you must surface only information that was explicitly spoken in the transcript. You are producing a legal medical record. Every field you populate must be directly traceable to specific words in the conversation. If a piece of information was never spoken by either party, the corresponding field must remain empty ([] for arrays, null for strings). An empty field is the correct output when the conversation has not covered that topic — it is never your role to fill gaps.

You are not a doctor. You have no medical opinion. You do not infer, suggest, predict, or complete information. You transcribe and categorize what was said, nothing more.

Extract the following JSON structure:
"keywords": An object containing:
   - "symptoms": Array of strings — only symptoms the PATIENT explicitly described or the DOCTOR explicitly confirmed observing. Use the speaker's own words.
   - "duration": String or null — only if a specific timeframe was stated (e.g., "for 3 days", "since Monday"). null if no duration was mentioned.
   - "root_cause": String or null — only if the DOCTOR explicitly stated a diagnosis or cause in the conversation. null if the doctor did not name one.
   - "prescriptions": Array of objects with "drug", "dose", and "frequency" — only medications the DOCTOR explicitly prescribed with those details spoken aloud. If no prescription was given, this must be an empty array.
   - "advice": Array of strings — only recommendations or next steps the DOCTOR explicitly communicated. If none were stated, this must be an empty array.

Return ONLY valid JSON. No markdown formatting, no commentary, no elaboration.

Example — notice that fields the conversation did not cover remain empty:
{
  "keywords": {
    "symptoms": ["severe headaches", "nausea"],
    "duration": "1 week",
    "root_cause": null,
    "prescriptions": [],
    "advice": []
  }
}
"""

EMPTY_KEYWORDS = {
    'symptoms': [], 'duration': None, 'root_cause': None,
    'prescriptions': [], 'advice': [],
}


def dialogue_from_transcribe(job_result: dict) -> tuple[str, list]:
    """Build a speaker-attributed dialogue from a completed Transcribe job.

    Returns (dialogue_text, speakers) where speakers is the ordered list of
    distinct speaker labels. The first speaker is treated as the doctor —
    in a consultation the doctor opens the conversation.
    """
    results = (job_result or {}).get('results', {})
    segments = (results.get('speaker_labels') or {}).get('segments', [])
    if not segments:
        text = ''
        for tr in results.get('transcripts', []):
            text += tr.get('transcript', '')
        return text, []

    turns = []
    current_speaker, current_words = None, []
    for seg in segments:
        spk = seg.get('speaker_label', 'spk_0')
        for item in seg.get('items', []):
            alt = (item.get('alternatives') or [{}])[0].get('content', '')
            if not alt:
                continue
            if item.get('type') == 'punctuation':
                if current_words:
                    current_words[-1] += alt
                continue
            if spk != current_speaker and current_words:
                turns.append((current_speaker, ' '.join(current_words)))
                current_words = []
            current_speaker = spk
            current_words.append(alt)
    if current_words:
        turns.append((current_speaker, ' '.join(current_words)))

    speakers = []
    for spk, _ in turns:
        if spk not in speakers:
            speakers.append(spk)

    def role(spk):
        return 'Doctor' if speakers.index(spk) == 0 else 'Patient'

    dialogue = '\n'.join(f'{role(spk)}: {text}' for spk, text in turns)
    return dialogue, speakers


def extract_structured(bedrock_client, model_id: str, dialogue: str) -> dict:
    """Call Bedrock with the verbatim-extraction prompt; return keywords dict."""
    if 'nova' in model_id:
        body = {
            'schemaVersion': 'messages-v1',
            'messages': [{
                'role': 'user',
                'content': [{'text': BEDROCK_SYSTEM_PROMPT + '\n\nTranscript:\n' + dialogue}],
            }],
            'inferenceConfig': {'temperature': 0.1, 'topP': 0.9, 'maxTokens': 1024},
        }
    else:  # Claude family (messages API)
        body = {
            'anthropic_version': 'bedrock-2023-05-31',
            'max_tokens': 1024,
            'system': BEDROCK_SYSTEM_PROMPT,
            'messages': [{'role': 'user', 'content': 'Transcript:\n' + dialogue}],
            'temperature': 0.1,
        }

    resp = bedrock_client.invoke_model(
        modelId=model_id, contentType='application/json', accept='application/json',
        body=json.dumps(body))
    payload = json.loads(resp['body'].read())
    if 'nova' in model_id:
        text = payload.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '')
    else:
        text = payload.get('content', [{}])[0].get('text', '')

    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = cleaned.strip('`')
        if cleaned.startswith('json'):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    start, end = cleaned.find('{'), cleaned.rfind('}')
    if start != -1 and end != -1:
        cleaned = cleaned[start:end + 1]

    data = json.loads(cleaned)
    keywords = data.get('keywords', data)
    out = dict(EMPTY_KEYWORDS)
    for k in out:
        if k in keywords:
            out[k] = keywords[k]
    return out


# ── rule-based fallback ──────────────────────────────────────────────────────
# Used when Bedrock is unavailable (e.g. pending account verification).
# Deliberately simple and transparent; the doctor reviews and approves
# everything either way.

_SYMPTOM_WORDS = [
    'headache', 'nausea', 'fever', 'cough', 'cold', 'sore throat', 'pain',
    'vomiting', 'dizziness', 'fatigue', 'rash', 'chest pain', 'breathless',
    'stomach ache', 'body ache', 'chills', 'congestion', 'diarrhea',
    'constipation', 'insomnia', 'swelling', 'itching', 'back pain',
]

_DURATION_RE = None  # compiled lazily below

import re

_DURATION_RE = re.compile(
    r'(?:for the past|for last|for|since|from)\s+(?:the\s+)?(?:last\s+)?'
    r'(\w+(?:\s+\w+){0,2}?)\s*(days?|weeks?|months?|hours?|years?)', re.I)
_PRESCRIPTION_RE = re.compile(
    r'(?:prescri\w+|take|giving|give)\s+([A-Z][\w-]*)\s*'
    r'(\d{1,4}\s*(?:mg|mcg|ml|g|units?|milligrams?|milligram))?.{0,40}?'
    r'(once|twice|three times|four times|\d+\s*times)?\s*(?:a\s+|per\s+)?'
    r'(daily|a day|after food|before food|every \d+ hours|at night|morning)?', re.I)


def rule_based_extract(dialogue: str) -> dict:
    lines = [l.strip() for l in dialogue.split('\n') if ':' in l]
    doctor_lines = [l.split(':', 1)[1].strip() for l in lines if l.lower().startswith('doctor')]
    patient_lines = [l.split(':', 1)[1].strip() for l in lines if l.lower().startswith('patient')]
    all_text = dialogue.lower()

    out = {'symptoms': [], 'duration': None, 'root_cause': None,
           'prescriptions': [], 'advice': []}

    for line in patient_lines + doctor_lines:
        low = line.lower()
        for w in _SYMPTOM_WORDS:
            if w in low and w not in [s.lower() for s in out['symptoms']]:
                out['symptoms'].append(w)

    m = _DURATION_RE.search(all_text)
    if m:
        out['duration'] = f'{m.group(1).strip()} {m.group(2).lower()}'.strip()

    for line in doctor_lines:
        low = line.lower()
        if out['root_cause'] is None:
            for cue in ('looks like', 'diagnos', 'you have', 'it is a', "it's a", 'suffering from', 'caused by'):
                idx = low.find(cue)
                if idx != -1:
                    out['root_cause'] = line[idx:].split('.')[0].split(',')[0].strip().rstrip('.-')
                    break

    for line in doctor_lines:
        for m in _PRESCRIPTION_RE.finditer(line):
            drug, dose, freq, sched = m.group(1), m.group(2), m.group(3), m.group(4)
            if not drug:
                continue
            low = (drug or '').lower()
            if low in ('plenty', 'lots', 'rest', 'water', 'it', 'this', 'that'):
                continue
            entry = {'drug': drug.strip(), 'dose': (dose or '').strip() or None,
                     'frequency': ' '.join(x for x in (freq, sched) if x) or None}
            if not any(p['drug'].lower() == low for p in out['prescriptions']):
                entry = {k: (v if v is not None else '') for k, v in entry.items()}
                out['prescriptions'].append(entry)

    for line in doctor_lines:
        low = line.lower()
        for cue in ('take plenty', 'take rest', 'rest and', 'drink ', 'avoid ',
                    'come back', 'return if', 'follow up', 'gargle', 'exercise'):
            if cue in low and line not in out['advice']:
                out['advice'].append(line)
                break

    return out


def extract_with_fallback(bedrock_client, model_id: str, dialogue: str) -> tuple[dict, str]:
    """Try Bedrock; fall back to the rule-based extractor. Returns (keywords, method)."""
    try:
        return extract_structured(bedrock_client, model_id, dialogue), 'bedrock'
    except Exception as bedrock_err:
        print(f'Bedrock extraction unavailable ({bedrock_err}) — using rule-based fallback')
        return rule_based_extract(dialogue), 'rule-based'
