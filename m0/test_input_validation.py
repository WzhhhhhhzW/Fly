"""Regression coverage for malformed packets; no vehicle commands."""
import json
import unittest

from protocol import MAX_BYTES, decode, encode, packet


class InputValidationTests(unittest.TestCase):
    def test_decode_rejects_nonfinite_numbers(self):
        for value in ('NaN', 'Infinity', '-Infinity', '1e309', '-1e309'):
            with self.subTest(value=value):
                data = (b'{"version":1,"node":"car","session":"s","seq":0,'
                        b'"type":"PING","t_ms":0,"payload":{"values":['
                        + value.encode('ascii') + b']}}')
                with self.assertRaises(ValueError):
                    decode(data)

    def test_decode_reports_deep_nesting_as_value_error(self):
        data = b'[' * 1000 + b'0' + b']' * 1000
        self.assertLessEqual(len(data), MAX_BYTES)
        with self.assertRaises(ValueError):
            decode(data)

    def test_finite_nested_numbers_roundtrip(self):
        message = packet('car', 'finite', 1, 'PING',
                         {'values': [1.25, -1e200, {'small': 1e-200}]})
        self.assertEqual(decode(encode(message)), message)

    def test_decode_rejects_bad_utf8_and_nonobject_json(self):
        for data in (b'\xff', b'[]', b'null', b'"text"', b'{'):
            with self.subTest(data=data):
                with self.assertRaises((ValueError, UnicodeError)):
                    decode(data)

    def test_decode_rejects_oversized_packet(self):
        with self.assertRaises(ValueError):
            decode(b' ' * (MAX_BYTES + 1))


if __name__ == '__main__':
    unittest.main()
