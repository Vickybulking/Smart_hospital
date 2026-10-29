# 🎓 Carely — Review-Day Runbook

Everything you need to start up and demo the system **by yourself**.
Print this page or keep it open on your phone.

---

## 1. What is running where

| Piece | Where | Needs starting? |
|---|---|---|
| AWS stack (`carely-dev`) | Your AWS account `560461522735`, region **Sydney (ap-southeast-2)** | **No — always on.** Nothing to restart, no session to renew. |
| Frontend (web page) | Any computer with Python 3 | **Yes — one command** (Section 3) |
| Login | Handled by real Amazon Cognito | No setup — just credentials below |

The browser talks **directly** to AWS (Cognito + API Gateway). No AWS credentials,
no CLI, no login to AWS is needed on review day — only the one command in step 3.

---

## 2. The repository (one-time check)

The code lives at:
`/Users/vickybulking/.zcode/workspace/81f5f970-51f8-4a8f-a612-89e4a1c875a5/Smart_hospital`

And on GitHub: https://github.com/Vickybulking/Smart_hospital

`frontend/config.js` already points at the live AWS stack (it is *not* in git —
it stays on this machine). Its correct contents are:

```js
window.CARELY_CONFIG = {
  apiUrl: 'https://mzwfyj758l.execute-api.ap-southeast-2.amazonaws.com/development',
  region: 'ap-southeast-2',
  userPoolId: 'ap-southeast-2_cjNvN5xb9',
  userPoolClientId: '1ckvo8kdg6185k6ap7o4jjapq1',
};
```

If this file is ever missing, create `frontend/config.js` with exactly that content.

---

## 3. Starting up on review day (2 minutes)

```bash
cd /Users/vickybulking/.zcode/workspace/81f5f970-51f8-4a8f-a612-89e4a1c875a5/Smart_hospital
python3 -m http.server 8080 --directory frontend
```

You should see: `Serving HTTP on 0.0.0.0 port 8080`. **Leave this terminal open.**

Then open **Google Chrome** → http://localhost:8080

⚠️ Use Chrome, not Safari and not any embedded preview — live dictation
only works in Chrome.

---

## 4. Login credentials (real Cognito accounts)

| Role | Email | Password |
|---|---|---|
| Patient | priya.patient@carely.demo | Patient#123 |
| Patient 2 | rahul.patient@carely.demo | Patient#123 |
| Doctor | maya.doctor@carely.demo | Doctor#123 |
| Admin | admin@carely.demo | Admin#123 |

---

## 5. The demo script (10 minutes)

### Part A — Patient books (Priya)
1. Sign in as **priya.patient@carely.demo**
2. Dashboard shows her live profile (Blood group O+ — real DynamoDB data)
3. **Book appointment** → Dr. Maya Patel → pick tomorrow → choose a slot → Confirm
4. **My appointments** → status is **pending**

### Part B — Doctor approves (Maya)
5. Sign out → sign in as **maya.doctor@carely.demo**
6. **Appointment requests** → Priya's request is there → **Accept**
7. **Patient records** → write a record: title + notes → Save

### Part C — Voice reports ⭐ (the unique feature)
8. Still as Maya → **Voice reports** → patient Priya
9. **🎙 Start live dictation** → allow mic if asked → speak the script (Section 6),
   tapping **"Next line: Doctor ⇄"** between speakers
10. **🧠 Generate AI medical report** → the structured report appears:
    symptoms, duration, diagnosis, prescriptions, advice
11. Review it → **✓ Approve report**

### Part D — Patient sees everything (Priya)
12. Sign out → sign in as **priya.patient@carely.demo**
13. **Medical reports** → the approved report is there → **Open report**
14. **Medical records** → Maya's record from step 7
15. Bonus: show **admin@carely.demo** → all doctors/patients/appointments

### Part E — Safety feature (optional, impressive)
16. As **rahul.patient@carely.demo**, try booking the **same slot** Priya just
    booked → the system rejects it: *"That doctor slot is already booked"* —
    double-booking prevention via DynamoDB transactions.

---

## 6. Dictation script (speak this in step 9)

> **Doctor:** Hello! What brings you in today?
> **Patient:** Doctor, I have had a severe sore throat and fever since the past three days. Swallowing food is also quite painful.
> **Doctor:** Let me take a look… I can see white patches on your tonsils. It looks like acute bacterial tonsillitis.
> **Doctor:** I will prescribe Amoxicillin, five hundred milligrams, three times daily for five days. For the fever and pain, you can take Paracetamol, five hundred milligrams, every six hours if needed.
> **Patient:** Okay doctor.
> **Doctor:** Take plenty of rest and drink lots of warm water. Gargle with warm salt water twice a day. And come back if the fever does not settle within three days.

Rhythm: speak one line → **see it appear** in the transcript → tap the
speaker toggle → speak the next line. Doses spoken explicitly ("five hundred
milligrams") make the prescription table populate perfectly. The transcript
box is editable — fix any word before generating.

---

## 7. Troubleshooting (everything we've ever hit)

| Symptom | Fix |
|---|---|
| Sidebar missing "Voice reports" | Stale cache → **Cmd+Shift+R** (hard refresh) |
| Dashboard says "Failed to fetch" | CloudFront cached an old error → wait 2 min, reload. Fresh paths work immediately. |
| "❌ Microphone blocked" | Click the 🔒 in Chrome's address bar → Microphone → Allow → reload |
| "❌ Speech service needs internet" | Google's speech endpoint blocked on this network → switch to **phone hotspot**, or just type the transcript instead |
| Dictation lines repeat twice | Fixed in current code — hard refresh. Old lines can also be deleted by hand in the transcript box |
| Booking says "slot already booked" | That's the anti-double-booking feature — pick a different slot |
| Login says wrong password | Check the table above (patient vs doctor passwords differ) |
| Terminal says "Address already in use" | The server is already running — just open Chrome |
| Page completely blank | Server died → repeat Section 3 |

**The unbreakable fallback:** if live dictation fails on stage, **type or paste**
the dialogue from Section 6 into the transcript box (prefix lines `Doctor:` /
`Patient:`) → Generate → identical report through the identical pipeline.

---

## 8. Emergency: full redeploy (only if the stack was deleted)

The CLI profile `vicky` is already configured on this machine
(`~/.aws/credentials`) and its access key does not expire.

```bash
cd /Users/vickybulking/.zcode/workspace/81f5f970-51f8-4a8f-a612-89e4a1c875a5/Smart_hospital
AWS_PROFILE=vicky bash scripts/deploy.sh carely-dev ap-southeast-2 development vicky
```

This rebuilds, deploys, fixes CORS OPTIONS methods, regenerates
`frontend/config.js`, and re-seeds the demo users (~8 minutes).

On a brand-new machine instead:
1. `git clone https://github.com/Vickybulking/Smart_hospital`
2. Create `frontend/config.js` with the content from Section 2
3. `python3 -m http.server 8080 --directory frontend`

---

## 9. After the review — cost control

The stack is pay-per-request and costs pennies at demo scale. To tear
everything down when the course ends:

```bash
AWS_PROFILE=vicky sam delete --stack-name carely-dev --region ap-southeast-2
```

Also remember to remove the demo Cognito users / empty the documents bucket
if you want a fully clean account.
