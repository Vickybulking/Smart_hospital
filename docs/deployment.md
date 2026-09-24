# Deployment Documentation

## Prerequisites
- AWS CLI configured
- SAM CLI installed
- Python 3.9+

## Deployment Steps
1. `sam build`
2. `sam deploy --guided`
3. Configure Cognito settings
4. Set up DynamoDB tables
5. Deploy frontend to S3

## Environment Configuration
- Copy `.env.example` to `.env`
- Fill in AWS resource IDs
- Deploy with appropriate profile
