#!/usr/bin/env python3
"""Seed Carely with synthetic demo data.

Creates three Cognito users (patient, doctor, admin) with fixed demo
passwords, assigns their groups, and writes matching DynamoDB profiles.
Doctor profiles are keyed by the doctor's Cognito sub so the doctor can
manage their own availability through the API.

Run AFTER a successful deployment:
    python3 scripts/seed_data.py --stack carely-dev

All data is synthetic — never use real patient information in demos.
"""

import argparse
import sys
from datetime import datetime, timezone

import boto3

DEMO_USERS = [
    {
        'email': 'priya.patient@carely.demo',
        'password': 'Patient#123',
        'name': 'Priya Sharma',
        'group': 'patient',
        'profile': 'patient',
    },
    {
        'email': 'maya.doctor@carely.demo',
        'password': 'Doctor#123',
        'name': 'Dr. Maya Patel',
        'group': 'doctor',
        'profile': 'doctor',
        'specialty': 'Cardiology',
        'qualification': 'MBBS, MD (Cardiology)',
        'experience': '12 years',
        'availability': {
            'monday': ['09:00', '10:30', '14:00'],
            'wednesday': ['09:00', '10:30', '14:00'],
            'friday': ['09:00', '10:30', '14:00'],
        },
    },
    {
        'email': 'admin@carely.demo',
        'password': 'Admin#123',
        'name': 'Amir Administrator',
        'group': 'admin',
        'profile': None,
    },
]


def stack_outputs(cfn, stack_name):
    stack = cfn.describe_stacks(StackName=stack_name)['Stacks'][0]
    return {o['OutputKey']: o['OutputValue'] for o in stack['Outputs']}


def stack_resource_id(cfn, stack_name, logical_id):
    resources = cfn.describe_stack_resources(StackName=stack_name)['StackResources']
    for r in resources:
        if r['LogicalResourceId'] == logical_id:
            return r['PhysicalResourceId']
    raise RuntimeError(f'Resource {logical_id} not found in stack {stack_name}')


def ensure_user(cognito, pool_id, email, password, name):
    try:
        resp = cognito.admin_get_user(UserPoolId=pool_id, Username=email)
        sub = next((a['Value'] for a in resp['UserAttributes'] if a['Name'] == 'sub'), None)
        print(f'  [exists] {email}')
        return sub
    except cognito.exceptions.UserNotFoundException:
        pass

    resp = cognito.admin_create_user(
        UserPoolId=pool_id,
        Username=email,
        UserAttributes=[
            {'Name': 'email', 'Value': email},
            {'Name': 'email_verified', 'Value': 'true'},
            {'Name': 'name', 'Value': name},
        ],
        MessageAction='SUPPRESS',  # no invitation email — demo accounts
    )
    sub = resp['User']['Attributes'] and next(
        a['Value'] for a in resp['User']['Attributes'] if a['Name'] == 'sub')
    cognito.admin_set_user_password(
        UserPoolId=pool_id, Username=email, Password=password, Permanent=True)
    print(f'  [created] {email}')
    return sub


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stack', default='carely-dev', help='CloudFormation stack name')
    args = parser.parse_args()

    session = boto3.Session()
    cfn = session.client('cloudformation')
    cognito = session.client('cognito-idp')
    dynamodb = session.resource('dynamodb')

    outputs = stack_outputs(cfn, args.stack)
    pool_id = outputs['CognitoUserPoolId']
    region = outputs.get('Region', session.region_name)
    print(f'Seeding stack {args.stack} (pool {pool_id}, region {region})')

    patients_table = dynamodb.Table(stack_resource_id(cfn, args.stack, 'PatientsTable'))
    doctors_table = dynamodb.Table(stack_resource_id(cfn, args.stack, 'DoctorsTable'))

    for user in DEMO_USERS:
        print(f'User {user["email"]} ({user["group"]}):')
        sub = ensure_user(cognito, pool_id, user['email'], user['password'], user['name'])

        cognito.admin_add_user_to_group(
            UserPoolId=pool_id, Username=user['email'], GroupName=user['group'])

        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        if user['profile'] == 'patient':
            patients_table.put_item(Item={
                'patientId': sub,
                'name': user['name'],
                'email': user['email'],
                'phone': '+91 98765 43210',
                'dateOfBirth': '1998-04-12',
                'bloodGroup': 'O+',
                'allergies': 'None known',
                'emergencyContact': 'Raj Sharma · +91 98765 43211',
                'role': 'patient',
                'createdAt': now,
                'updatedAt': now,
            })
            print('  [profile] patient row written')
        elif user['profile'] == 'doctor':
            doctors_table.put_item(Item={
                'doctorId': sub,
                'name': user['name'],
                'email': user['email'],
                'specialty': user['specialty'],
                'qualification': user.get('qualification', ''),
                'experience': user.get('experience', ''),
                'bio': '',
                'phone': '',
                'availability': user.get('availability', {}),
                'role': 'doctor',
                'createdAt': now,
                'updatedAt': now,
            })
            print('  [profile] doctor row written')

    print('\nSeed complete. Demo credentials:')
    for user in DEMO_USERS:
        print(f'  {user["group"]:>7}: {user["email"]}  /  {user["password"]}')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'Seed failed: {e}', file=sys.stderr)
        sys.exit(1)
