# Architecture Documentation

## Overview
Smart Hospital Management System built on AWS serverless architecture.

## AWS Services
- Frontend: S3 + CloudFront
- Authentication: Amazon Cognito
- API: API Gateway
- Backend: AWS Lambda
- Database: DynamoDB
- Documents: S3
- Notifications: SNS / SES
- Monitoring: CloudWatch
- Permissions: IAM
- AI Feature: Amazon Bedrock (optional)

## Data Flow
Frontend → Cognito → API Gateway → Lambda → DynamoDB/S3/SNS
