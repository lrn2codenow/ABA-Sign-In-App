"""Netlify Function entry point for the ABA Sign-In application."""

import base64
from typing import Dict

from app import AppResponse, ROUTER
from http import HTTPStatus


def _serialize_body(response: AppResponse) -> Dict[str, object]:
    body_bytes = response.body or b''
    headers = {str(k): str(v) for k, v in response.headers.items()}
    content_type = headers.get('Content-Type', '')
    is_binary = False
    if not body_bytes:
        body_str = ''
    else:
        lower_type = content_type.lower()
        if lower_type.startswith('text/') or 'charset=' in lower_type:
            body_str = body_bytes.decode('utf-8')
        elif lower_type in {'application/json', 'application/javascript'}:
            body_str = body_bytes.decode('utf-8')
        else:
            body_str = base64.b64encode(body_bytes).decode('ascii')
            is_binary = True
    status_code = response.status.value if isinstance(response.status, HTTPStatus) else int(response.status)
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': body_str,
        'isBase64Encoded': is_binary,
    }


def handler(event, context):  # pragma: no cover - exercised via integration tests
    method = event.get('httpMethod', 'GET')
    raw_path = event.get('rawUrl') or event.get('rawPath') or event.get('path', '/')
    headers = event.get('headers') or {}
    body = event.get('body') or ''
    if event.get('isBase64Encoded'):
        body_bytes = base64.b64decode(body)
    else:
        body_bytes = body.encode('utf-8')
    response = ROUTER.handle(method, raw_path, headers, body_bytes)
    payload = _serialize_body(response)
    if method.upper() == 'HEAD':
        payload['body'] = ''
        payload['isBase64Encoded'] = False
    return payload
