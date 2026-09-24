# Database Design

## DynamoDB Tables

### Patients Table
- Partition Key: patientId (String)
- Sort Key: None
- Attributes: name, email, phone, role, createdAt, updatedAt

### Doctors Table
- Partition Key: doctorId (String)
- Sort Key: None
- Attributes: name, email, specialty, availability, createdAt, updatedAt

### Appointments Table
- Partition Key: appointmentId (String)
- Sort Key: None
- Attributes: patientId, doctorId, dateTime, status, type, createdAt, updatedAt

### MedicalRecords Table
- Partition Key: recordId (String)
- Sort Key: None
- Attributes: patientId, doctorId, title, contentUrl, createdAt, updatedAt
