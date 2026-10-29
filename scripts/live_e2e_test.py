#!/usr/bin/env python3
"""Live E2E test against the deployed AWS stack (carely-dev, ap-southeast-2)."""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

import boto3

API = "https://mzwfyj758l.execute-api.ap-southeast-2.amazonaws.com/development"
CLIENT_ID = "1ckvo8kdg6185k6ap7o4jjapq1"
REGION = "ap-southeast-2"
POOL = "ap-southeast-2_cjNvN5xb9"

session = boto3.Session(profile_name="vicky", region_name=REGION)
cognito = session.client("cognito-idp")

results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'✓ PASS' if ok else '✗ FAIL'}  {name}  {detail}")


def api(method, path, token=None, body=None):
    req = urllib.request.Request(f"{API}{path}", method=method)
    req.add_header("Content-Type", "application/json")
    if token:
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
    r = cognito.initiate_auth(
        ClientId=CLIENT_ID,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )
    return r["AuthenticationResult"]["IdToken"]


# ── setup: ensure a second patient exists (mimics a real signup) ─────────────
try:
    r = cognito.admin_create_user(
        UserPoolId=POOL, Username="rahul.patient@carely.demo",
        UserAttributes=[{"Name": "email", "Value": "rahul.patient@carely.demo"},
                        {"Name": "email_verified", "Value": "true"},
                        {"Name": "name", "Value": "Rahul Mehta"}],
        MessageAction="SUPPRESS")
except cognito.exceptions.UsernameExistsException:
    pass
cognito.admin_set_user_password(UserPoolId=POOL, Username="rahul.patient@carely.demo",
                                Password="Patient#123", Permanent=True)
try:
    cognito.admin_add_user_to_group(UserPoolId=POOL, Username="rahul.patient@carely.demo", GroupName="patient")
except Exception:
    pass
print("setup: second patient ready")

priya = token_for("priya.patient@carely.demo", "Patient#123")
maya = token_for("maya.doctor@carely.demo", "Doctor#123")
admin = token_for("admin@carely.demo", "Admin#123")
rahul = token_for("rahul.patient@carely.demo", "Patient#123")
print("setup: all four tokens acquired from real Cognito\n")

# ── 1. doctors list ──────────────────────────────────────────────────────────
st, body = api("GET", "/doctors", priya)
check("GET /doctors (patient)", st == 200 and body.get("count", 0) >= 1, f"status={st} count={body.get('count')}")
doctor_id = body["doctors"][0]["doctorId"]

# ── 2. booking ───────────────────────────────────────────────────────────────
slot = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d") + "T09:00:00Z"
st, body = api("POST", "/appointments", priya,
               {"patientId": "x", "doctorId": doctor_id, "dateTime": slot, "reason": "E2E live test"})
check("POST /appointments (patient books)", st in (200, 201), f"status={st}")
appt_id = body.get("appointmentId", "")

# ── 3. double-booking rejected ───────────────────────────────────────────────
st, body = api("POST", "/appointments", rahul,
               {"patientId": "x", "doctorId": doctor_id, "dateTime": slot, "reason": "sneaky"})
check("POST same slot (other patient) -> 409", st == 409, f"status={st} body={body}")

# ── 4. doctor sees and approves ──────────────────────────────────────────────
st, body = api("GET", "/appointments", maya)
mine = [a for a in body.get("appointments", []) if a["appointmentId"] == appt_id]
check("GET /appointments (doctor, role-scoped)", st == 200 and len(mine) == 1, f"status={st}")
st, body = api("PUT", f"/appointments/{appt_id}/approval", maya, {"decision": "confirmed"})
check("PUT approval (doctor confirms)", st == 200, f"status={st} body={body}")

# ── 5. patient cancels; slot released ────────────────────────────────────────
st, body = api("DELETE", f"/appointments/{appt_id}", priya)
check("DELETE /appointments (patient cancels)", st == 200, f"status={st}")
st, body = api("POST", "/appointments", rahul,
               {"patientId": "x", "doctorId": doctor_id, "dateTime": slot, "reason": "rebook after release"})
check("POST freed slot (rebook) -> 201", st in (200, 201), f"status={st}")
appt2 = body.get("appointmentId", "")

# ── 6. RBAC ──────────────────────────────────────────────────────────────────
st, _ = api("GET", "/patients", priya)
check("GET /patients (patient) -> 403", st == 403, f"status={st}")
st, body = api("GET", "/patients", admin)
check("GET /patients (admin) -> 200", st == 200, f"status={st} count={body.get('count')}")
priya_sub = None
r = cognito.admin_get_user(UserPoolId=POOL, Username="priya.patient@carely.demo")
priya_sub = next(a["Value"] for a in r["UserAttributes"] if a["Name"] == "sub")
st, _ = api("GET", f"/patients/{priya_sub}", rahul)
check("GET other patient's profile -> 403", st == 403, f"status={st}")

# ── 7. medical records ───────────────────────────────────────────────────────
st, body = api("POST", "/medical-records", maya,
               {"patientId": priya_sub, "title": "E2E consultation", "notes": "All normal.", "type": "consultation"})
check("POST /medical-records (doctor authors)", st in (200, 201), f"status={st}")
record_id = body.get("recordId", "")
st, body = api("GET", "/medical-records", priya)
found = any(r_.get("recordId") == record_id for r_ in body.get("records", []))
check("GET /medical-records (patient sees own)", st == 200 and found, f"status={st}")
st, _ = api("GET", f"/medical-records/{record_id}", rahul)
check("GET other patient's record -> 403", st == 403, f"status={st}")

# ── 8. documents (real S3 presigned flow) ────────────────────────────────────
st, body = api("POST", "/documents/upload-url", priya,
               {"contentType": "text/plain", "patientId": priya_sub})
check("POST /documents/upload-url", st == 200, f"status={st}")
upload_url, file_key = body["uploadUrl"], body["fileKey"]
req = urllib.request.Request(upload_url, method="PUT", data=b"live E2E document body")
req.add_header("Content-Type", "text/plain")
try:
    with urllib.request.urlopen(req) as r:
        upload_status = r.status
except urllib.error.HTTPError as e:
    if e.code in (301, 302, 307):
        # S3 redirects virtual-hosted global endpoints to the regional one;
        # re-issue the same PUT at the Location target.
        req2 = urllib.request.Request(e.headers["Location"], method="PUT", data=b"live E2E document body")
        req2.add_header("Content-Type", "text/plain")
        with urllib.request.urlopen(req2) as r:
            upload_status = r.status
    else:
        upload_status = e.code
check("PUT bytes to real S3 presigned URL", upload_status == 200, f"status={upload_status}")
st, body = api("POST", "/documents/metadata", priya,
               {"patientId": priya_sub, "fileKey": file_key, "fileName": "e2e-test.txt", "contentType": "text/plain"})
check("POST /documents/metadata", st in (200, 201), f"status={st}")
st, body = api("GET", "/documents", priya)
check("GET /documents (patient list)", st == 200 and body.get("count", 0) >= 1, f"status={st}")
import urllib.parse
st, body = api("GET", f"/documents/download-url?fileKey={urllib.parse.quote(file_key)}", priya)
check("GET /documents/download-url", st == 200, f"status={st}")

# ── summary ──────────────────────────────────────────────────────────────────
passed = sum(1 for _, ok in results if ok)
print(f"\n{'='*50}\nLIVE E2E: {passed}/{len(results)} PASSED\n{'='*50}")
sys.exit(0 if passed == len(results) else 1)
