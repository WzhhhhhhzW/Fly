"""Host-only CLI and UDP regression tests, bound to loopback."""
import contextlib
import io
import json
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

import linkcheck
from protocol import decode, encode, packet

SCRIPT = Path(__file__).with_name('linkcheck.py')


class ArgumentTests(unittest.TestCase):
    def assert_rejected(self, role, option, value):
        argv = ['linkcheck.py', role]
        if role == 'probe':
            argv += ['--host', '127.0.0.1']
        argv += [option + '=' + value]
        with patch.object(sys, 'argv', argv), \
                patch.object(linkcheck, 'listen') as listener, \
                patch.object(linkcheck, 'probe') as sender, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                linkcheck.main()
            self.assertEqual(caught.exception.code, 2)
            listener.assert_not_called()
            sender.assert_not_called()

    def test_rejects_nonfinite_and_nonpositive_timeout(self):
        for value in ('nan', 'inf', '-inf', '0', '-0.01'):
            with self.subTest(value=value):
                self.assert_rejected('probe', '--timeout', value)

    def test_rejects_nonfinite_and_nonpositive_duration(self):
        for value in ('nan', 'inf', '-inf', '0', '-0.01'):
            with self.subTest(value=value):
                self.assert_rejected('listen', '--duration', value)

    def test_positive_times_dispatch(self):
        for role, option in (('listen', '--duration'), ('probe', '--timeout')):
            argv = ['linkcheck.py', role, option + '=0.2']
            if role == 'probe':
                argv += ['--host', '127.0.0.1']
            with self.subTest(role=role), patch.object(sys, 'argv', argv), \
                    patch.object(linkcheck, role, return_value=0) as dispatch:
                self.assertEqual(linkcheck.main(), 0)
                dispatch.assert_called_once()


class LoopbackTests(unittest.TestCase):
    def start_listener(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, '-u', str(SCRIPT), 'listen', '--host', '127.0.0.1',
             '--port', str(port), '--duration', '2'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_listener, process)
        ready = queue.Queue()
        threading.Thread(target=lambda: ready.put(process.stdout.readline()),
                         daemon=True).start()
        try:
            line = ready.get(timeout=5)
        except queue.Empty:
            self.fail('listener did not become ready')
        self.assertTrue(line, 'listener exited before readiness')
        self.assertEqual(json.loads(line)['listening'], ['127.0.0.1', port])
        return process, port

    @staticmethod
    def stop_listener(process):
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)

    def test_listener_survives_malformed_packets(self):
        process, port = self.start_listener()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.settimeout(1)
            destination = ('127.0.0.1', port)
            for bad in (b'[' * 1000 + b'0' + b']' * 1000, b'\xff', b'{',
                        b'x' * 2049):
                sender.sendto(bad, destination)
            sender.sendto(encode(packet('car', 'after-bad', 7, 'PING')),
                          destination)
            data, addr = sender.recvfrom(2049)
            ack = decode(data)
            self.assertEqual(addr, destination)
            self.assertEqual(ack['type'], 'ACK')
            self.assertEqual(ack['session'], 'after-bad')
            self.assertEqual(ack['payload'], {'ack_seq': 7, 'ack_type': 'PING'})
            self.assertIsNone(process.poll())

    def test_probe_and_listener_loopback(self):
        process, port = self.start_listener()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), 'probe', '--host', '127.0.0.1',
             '--port', str(port), '--count', '3', '--timeout', '0.5'],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['sent'], 3)
        self.assertEqual(report['acknowledged'], 3)
        output, errors = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, errors)
        self.assertEqual(json.loads(output)['ping_received'], 3)


if __name__ == '__main__':
    unittest.main()
