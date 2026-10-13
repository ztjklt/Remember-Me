"""Explicit QA-only agent dispatch, preserving the authorized ticket grants."""
import base64
import copy
import hashlib
import hmac
import json
import re


def dispatch_ticket(ticket, agent_name, private):
    if not agent_name:
        return ticket
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', agent_name):
        raise ValueError('Invalid QA agent name')
    values = {}
    for line in (private / 'realtime.env').read_text().splitlines():
        key, separator, value = line.partition('=')
        if separator and key in {'REMEMBER_LIVEKIT_API_KEY', 'REMEMBER_LIVEKIT_API_SECRET'}:
            value = value.strip()
            if len(value) > 1 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            values[key] = value
    parts = ticket['token'].split('.')
    if len(parts) != 3:
        raise ValueError('Invalid ticket')
    secret = values['REMEMBER_LIVEKIT_API_SECRET'].encode()
    signature = base64.urlsafe_b64decode(parts[2] + '=' * (-len(parts[2]) % 4))
    if not hmac.compare_digest(signature, hmac.new(secret, '.'.join(parts[:2]).encode(), hashlib.sha256).digest()):
        raise ValueError('Ticket signature mismatch')
    decode = lambda part: json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
    header, claims = decode(parts[0]), decode(parts[1])
    if (header.get('alg') != 'HS256' or claims.get('iss') != values['REMEMBER_LIVEKIT_API_KEY']
            or claims.get('sub') != ticket['participant_identity']
            or claims.get('video', {}).get('room') != ticket['room']
            or ticket['room'] != ticket['call_id']
            or claims['video'].get('canPublishSources') != ['microphone']):
        raise ValueError('Ticket grants mismatch')
    changed = copy.deepcopy(claims)
    agents = changed['roomConfig']['agents']
    if len(agents) != 1 or json.loads(agents[0]['metadata']) != {'call_id': ticket['call_id']}:
        raise ValueError('Ticket call metadata mismatch')
    original_name = agents[0]['agentName']
    agents[0]['agentName'] = agent_name
    # No other claim, room, participant, expiry or media grant may change.
    stripped = copy.deepcopy(changed)
    stripped['roomConfig']['agents'][0]['agentName'] = original_name
    if stripped != claims:
        raise ValueError('Unexpected ticket change')
    encoded = base64.urlsafe_b64encode(json.dumps(changed, separators=(',', ':')).encode()).rstrip(b'=').decode()
    body = parts[0] + '.' + encoded
    signed = base64.urlsafe_b64encode(hmac.new(secret, body.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
    return dict(ticket, token=body + '.' + signed)
