import unittest
from protocol import StartDeduplicator, decode, encode, packet

class ProtocolTests(unittest.TestCase):
    def test_roundtrip(self):
        message = packet('car', 'test-session', 1, 'PING')
        self.assertEqual(decode(encode(message)), message)

    def test_duplicate_start(self):
        seen = StartDeduplicator()
        message = packet('car', 'test-session', 1, 'START', {'mode': 'drop'})
        self.assertTrue(seen.is_new(message))
        self.assertFalse(seen.is_new(decode(encode(message))))

    def test_invalid_sender(self):
        with self.assertRaises(ValueError):
            packet('ground', 'test-session', 1, 'START', {'mode': 'drop'})

    def test_missing_ack_reference(self):
        with self.assertRaises(ValueError):
            packet('drone', 'test-session', 1, 'ACK', {})

    def test_bad_version_and_boolean_sequence(self):
        message = packet('car', 'test-session', 1, 'PING')
        for key, value in [('version', 99), ('seq', True)]:
            bad = dict(message, **{key: value})
            with self.assertRaises(ValueError):
                encode(bad)

    def test_oversize(self):
        message = packet('car', 'test-session', 1, 'PING', {'extra': 'x' * 2048})
        with self.assertRaises(ValueError):
            encode(message)

if __name__ == '__main__':
    unittest.main()
