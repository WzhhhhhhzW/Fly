"""Safe UDP PING/ACK only: never sends START or commands flight hardware."""
import argparse
import json
import math
import socket
import time
import uuid
from protocol import MAX_BYTES, decode, encode, packet

def listen(args):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((args.host, args.port))
        print(json.dumps({'listening': [args.host, args.port], 'node': args.node}), flush=True)
        sock.settimeout(0.25)
        end = time.monotonic() + args.duration
        received = 0
        while time.monotonic() < end:
            try:
                data, addr = sock.recvfrom(MAX_BYTES + 1)
            except socket.timeout:
                continue
            try:
                message = decode(data)
                if message['type'] != 'PING':
                    continue
                reply = packet(args.node, message['session'], received, 'ACK',
                               {'ack_seq': message['seq'], 'ack_type': 'PING'})
                sock.sendto(encode(reply), addr)
                received += 1
            except (ValueError, UnicodeError, TypeError):
                continue
        print(json.dumps({'role': 'listen', 'ping_received': received}))

def probe(args):
    session = uuid.uuid4().hex
    destination = (socket.gethostbyname(args.host), args.port)
    rtts = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for seq in range(args.count):
            start = time.monotonic()
            start_ns = time.perf_counter_ns()
            sock.sendto(encode(packet(args.node, session, seq, 'PING')), destination)
            deadline = start + args.timeout
            while time.monotonic() < deadline:
                sock.settimeout(max(0.001, deadline - time.monotonic()))
                try:
                    data, addr = sock.recvfrom(MAX_BYTES + 1)
                except socket.timeout:
                    break
                try:
                    ack = decode(data)
                    if addr == destination and ack['type'] == 'ACK' and ack['session'] == session and ack['payload'] == {'ack_seq': seq, 'ack_type': 'PING'}:
                        rtts.append((time.perf_counter_ns() - start_ns) / 1000000)
                        break
                except (ValueError, UnicodeError, TypeError):
                    continue
            time.sleep(0.05)
    result = {'role': 'probe', 'destination': destination, 'sent': args.count,
              'acknowledged': len(rtts), 'rtt_max_ms': round(max(rtts), 3) if rtts else None,
              'scope': 'PING/ACK only; not power, positioning or flight verification'}
    print(json.dumps(result))
    return 0 if len(rtts) == args.count else 1

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='role', required=True)
    receiver = commands.add_parser('listen')
    receiver.add_argument('--host', default='127.0.0.1')
    receiver.add_argument('--port', type=int, default=14560)
    receiver.add_argument('--duration', type=float, default=60)
    receiver.add_argument('--node', choices=['car', 'drone', 'ground'], default='drone')
    sender = commands.add_parser('probe')
    sender.add_argument('--host', required=True)
    sender.add_argument('--port', type=int, default=14560)
    sender.add_argument('--node', choices=['car', 'drone', 'ground'], default='car')
    sender.add_argument('--count', type=int, default=20)
    sender.add_argument('--timeout', type=float, default=1)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be 1..65535')
    if args.role == 'probe' and (args.count < 1 or not math.isfinite(args.timeout) or args.timeout <= 0):
        parser.error('positive count and finite positive timeout required')
    if args.role == 'listen' and (not math.isfinite(args.duration) or args.duration <= 0):
        parser.error('finite positive duration required')
    return listen(args) if args.role == 'listen' else probe(args)

if __name__ == '__main__':
    raise SystemExit(main())
