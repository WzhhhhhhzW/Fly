"""M0 application envelope; validation does not authorize vehicle actions."""
import json
import time

VERSION = 1
MAX_BYTES = 2048
NODES = {'car', 'drone', 'ground'}
TYPES = {'PING', 'ACK', 'READY', 'START', 'TELEMETRY'}

def integer(value):
    return type(value) is int and value >= 0

def validate(message):
    if not isinstance(message, dict):
        raise ValueError('packet must be an object')
    if type(message.get('version')) is not int or message['version'] != VERSION:
        raise ValueError('unsupported version')
    if message.get('node') not in NODES or message.get('type') not in TYPES:
        raise ValueError('invalid node or type')
    if not isinstance(message.get('session'), str) or not 1 <= len(message['session']) <= 64:
        raise ValueError('invalid session')
    if not integer(message.get('seq')) or not integer(message.get('t_ms')):
        raise ValueError('invalid sequence or timestamp')
    payload = message.get('payload')
    if not isinstance(payload, dict):
        raise ValueError('payload must be an object')
    kind = message['type']
    if kind == 'ACK' and (not integer(payload.get('ack_seq')) or payload.get('ack_type') not in TYPES):
        raise ValueError('invalid ACK')
    if kind == 'READY' and type(payload.get('ready')) is not bool:
        raise ValueError('invalid READY')
    if kind == 'START' and (message['node'] != 'car' or payload.get('mode') not in {'drop', 'dynamic'}):
        raise ValueError('invalid START')
    if kind == 'TELEMETRY' and (type(payload.get('valid')) is not bool or not isinstance(payload.get('state'), str) or not payload['state']):
        raise ValueError('invalid TELEMETRY')
    return message

def packet(node, session, seq, kind, payload=None):
    return validate(dict(version=VERSION, node=node, session=session, seq=seq,
                         type=kind, t_ms=time.monotonic_ns() // 1000000,
                         payload={} if payload is None else payload))

def encode(message):
    data = json.dumps(validate(message), ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(data) > MAX_BYTES:
        raise ValueError('packet too large')
    return data

def decode(data):
    if len(data) > MAX_BYTES:
        raise ValueError('packet too large')
    return validate(json.loads(data.decode('utf-8')))

class StartDeduplicator:
    """Application test helper; not a flight-ready startup state machine."""
    def __init__(self):
        self.seen = set()

    def is_new(self, message):
        validate(message)
        if message['type'] != 'START':
            raise ValueError('expected START')
        key = (message['session'], message['seq'])
        if key in self.seen:
            return False
        self.seen.add(key)
        return True
