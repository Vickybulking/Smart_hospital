# Smart Hospital Management System

A cloud-native hospital management system built with AWS serverless technologies.

## Frontend demo

The `frontend/` folder contains a no-build browser prototype for presentations. It demonstrates:

- role-based sign-in for patient, doctor, and admin accounts;
- patient profile fields and a visible confidentiality boundary;
- doctor availability and the patient appointment booking flow;
- duplicate-slot rejection in demo state;
- admin views for doctors, patients, appointments, users, and system activity.

Open `frontend/index.html` directly in a browser, or serve the folder with:

```bash
python3 -m http.server 8080 --directory frontend
```

Then visit http://localhost:8080. The prototype uses local in-memory demo data; connect the forms to the Cognito/API Gateway endpoints in `infrastructure/template.yaml` for deployment.
