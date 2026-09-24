import json


def claims(event):
    return ((event.get('requestContext') or {}).get('authorizer') or {}).get('claims') or {}


def user_sub(event):
    return claims(event).get('sub')


def groups(event):
    value = claims(event).get('cognito:groups', '')
    return value if isinstance(value, list) else [x for x in value.split(',') if x]


def is_group(event, group):
    return group in groups(event)


def response(status, body):
    return {'statusCode': status, 'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'}, 'body': json.dumps(body)}
