"""Cognito PostConfirmation trigger.

Every self-registered user is placed in the `patient` group. Doctor and
admin memberships are granted out-of-band by an operator (scripts/seed_data.py)
because letting the client pick a role at sign-up would let anyone grant
themselves administrative access.
"""

import json
import os

import boto3

cognito = boto3.client('cognito-idp')

DEFAULT_GROUP = 'patient'


def handler(event, context):
    """Add the confirmed user to the default patient group and return the event."""
    try:
        user_pool_id = event['userPoolId']
        username = event['userName']

        cognito.admin_add_user_to_group(
            UserPoolId=user_pool_id,
            Username=username,
            GroupName=DEFAULT_GROUP,
        )
        print(f"[PostConfirmation] Added user {username} to group '{DEFAULT_GROUP}'")
    except Exception as e:
        # Swallowing would silently drop group membership; raising lets Cognito
        # retry the trigger and surface the failure in CloudWatch instead.
        print(f"[PostConfirmation] Error assigning group: {e}")
        raise

    # PostConfirmation triggers must return the event unchanged for the
    # sign-up flow to complete.
    return event
