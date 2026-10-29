# Carely — Smart Hospital Management System (AWS Serverless)

A cloud-native hospital management system: Amazon Cognito authentication with
role-based access (patient / doctor / admin), API Gateway, Lambda, DynamoDB,
S3 for documents, SNS for notifications, and a Bedrock-assisted AI summary
endpoint. Frontend is a no-build browser app served as static files.

Base project: [Vickybulking/Smart_hospital](https://github.com/Vickybulking/Smart_hospital),
reworked for real AWS integration. The voice-to-report feature (Phase 4) will
draw on the [Friedlguana/conversationalAgent](https://github.com/Friedlguana/conversationalAgent)
medical-scribe prototype (Transcribe/Bedrock pipeline design).

## Repository layout

```
backend/functions/     one Lambda per API action (RBAC enforced in-code)
backend/shared/        auth helpers (Cognito claims), validators
frontend/              vanilla HTML/CSS/JS app (no build step)
infrastructure/        SAM template (template.yaml)
scripts/               deploy.sh, seed_data.py, update_frontend_config.sh
tests/unit/            handler unit tests (mocked boto3)
tests/integration/     full workflow test (moto DynamoDB, real transactions)
```

## Deploy

Prerequisites: AWS CLI + SAM CLI installed and authenticated, Python 3.10+.

```bash
sam build --template infrastructure/template.yaml
sam deploy --template .aws-sam/build/template.yaml \
  --stack-name carely-dev --region ap-southeast-2 \
  --capabilities CAPABILITY_IAM --resolve-s3 --no-confirm-changeset \
  --parameter-overrides EnvironmentName=development

scripts/update_frontend_config.sh carely-dev   # writes frontend/config.js
python3 scripts/seed_data.py --stack carely-dev # demo users + profiles
```

`scripts/deploy.sh` runs all four steps in sequence.

Teardown: `sam delete --stack-name carely-dev`.

## Run the frontend

```bash
python3 -m http.server 8080 --directory frontend
```

Open http://localhost:8080. After seeding, demo credentials:

| Role   | Email                      | Password     |
|--------|----------------------------|--------------|
| Patient| priya.patient@carely.demo  | Patient#123  |
| Doctor | maya.doctor@carely.demo    | Doctor#123   |
| Admin  | admin@carely.demo          | Admin#123    |

Self sign-up is also available in the UI (creates patient accounts only —
doctor/admin accounts are provisioned by an operator via `seed_data.py`).

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest tests/
```

107 tests: unit tests per handler plus an integration test that runs the
real handler code against moto-backed DynamoDB — it verifies the full core
workflow: profile creation, role enforcement, availability, booking,
double-booking rejection (409), doctor approval, cancellation with slot
release, and rebooking of the freed slot.

## Security notes

- All API routes require a Cognito JWT (API Gateway authorizer).
- Every handler re-checks role/group and object ownership server-side.
- Patients are always scoped to their own records (profile, appointments,
  medical records, documents prefix in S3).
- Doctor/medical-record authorship is pinned to the caller's Cognito sub.
- Appointment double-booking is prevented with a DynamoDB transaction that
  claims a `doctorId#dateTime` slot lock; cancellation/reschedule release or
  swap the lock atomically.
- New self-service sign-ups always land in the `patient` group (PostConfirmation
  trigger) — clients cannot choose a role.
- No AWS credentials exist in frontend code; the browser only holds Cognito
  JWT tokens. Use synthetic data only.
