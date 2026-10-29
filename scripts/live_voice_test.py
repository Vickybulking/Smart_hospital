#!/usr/bin/env python3
"""Live Phase-4 test: real speech -> Transcribe -> Bedrock -> structured report."""
import json
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

import boto3

API = "https://mzwfyj758l.execute-api.ap-southeast-2.amazonaws.com/development"
CLIENT_ID = "1ckvo8kdg6185k6ap7o4jjapq1"
REGION = "ap-southeast-2"
POOL = "ap-southeast-2_cjNvN5xb9"

session = boto3.Session(profile_name="vicky", region_name=REGION)
cognito = session.client("cognito-idp")


def api(method, path, token, body=None):
    req = urllib.request.Request(f"{API}{path}", method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def token_for(email, password):
    r = cognito.initiate_auth(ClientId=CLIENT_ID, AuthFlow="USER_PASSWORD_AUTH",
                              AuthParameters={"USERNAME": email, "PASSWORD": password})
    return r["AuthenticationResult"]["IdToken"]


maya = token_for("maya.doctor@carely.demo", "Doctor#123")
priya = token_for("priya.patient@carely.demo", "Patient#123")
print("tokens ok")

# patient sub for attribution
r = cognito.admin_get_user(UserPoolId=POOL, Username="priya.patient@carely.demo")
priya_sub = next(a["Value"] for a in r["UserAttributes"] if a["Name"] == "sub")

# ── upload the dialogue audio ────────────────────────────────────────────────
st, body = api("POST", "/voice-reports/upload-url", maya, {"contentType": "audio/wav"})
print("upload-url:", st)
upload_url, file_key = body["uploadUrl"], body["fileKey"]
wav = open("/tmp/consultation.wav", "rb").read()
req = urllib.request.Request(upload_url, method="PUT", data=wav)
req.add_header("Content-Type", "audio/wav")
try:
    with urllib.request.urlopen(req) as r:
        print("audio PUT:", r.status)
except urllib.error.HTTPError as e:
    if e.code in (301, 302, 307):
        req2 = urllib.request.Request(e.headers["Location"], method="PUT", data=wav)
        req2.add_header("Content-Type", "audio/wav")
        with urllib.request.urlopen(req2) as r:
            print("audio PUT (after redirect):", r.status)
    else:
        raise

# ── create the voice report (starts Transcribe) ─────────────────────────────
st, body = api("POST", "/voice-reports", maya,
               {"patientId": priya_sub, "audioKey": file_key, "audioFileName": "say-dialogue.wav"})
print("create:", st, body)
if st not in (200, 201):
    sys.exit(1)
report_id = body["reportId"]

# ── poll until Transcribe + Bedrock finish ───────────────────────────────────
final = None
for i in range(30):
    time.sleep(6)
    st, body = api("GET", f"/voice-reports/{report_id}", maya)
    rep = body.get("report", {})
    st_rep = rep.get("status")
    print(f"poll {i+1}: status={st_rep}", rep.get("errorMessage", ""))
    if st_rep != "transcribing":
        final = rep
        break

print("\n════════ TRANSCRIPT ════════")
print(final.get("transcript", "(none)"))
print("\n════════ BEDROCK EXTRACTION ════════")
print(json.dumps(final.get("structured"), indent=2, ensure_ascii=False))

if final.get("status") == "review":
    st, body = api("PUT", f"/voice-reports/{report_id}/approval", maya, {"decision": "approved"})
    print("\napprove:", st, body.get("status"))
    st, body = api("GET", f"/voice-reports/{report_id}", priya)
    print("patient can fetch approved report:", st == 200, "| status:", body.get("report", {}).get("status"))
    print("\nFULL PIPELINE: SPEECH -> TRANSCRIBE -> BEDROCK -> DOCTOR APPROVAL => WORKING")
else:
    print("\nPIPELINE DID NOT REACH REVIEW — inspect errorMessage above")
    sys.exit(1)
