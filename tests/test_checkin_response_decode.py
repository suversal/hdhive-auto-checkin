import time
import unittest

from scripts.checkin import decode_response_text


class FakeResponse:
    def __init__(self, body_bytes: bytes = b"", delay_seconds: float = 0) -> None:
        self.body_bytes = body_bytes
        self.delay_seconds = delay_seconds

    def body(self) -> bytes:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        return self.body_bytes


class DecodeResponseTextTest(unittest.TestCase):
    def test_decodes_next_action_chunks(self) -> None:
        response = FakeResponse(
            b'0:{"a":"$@1"}\n'
            b'1:{"error":{"success":false,"message":"failed","description":"already done"}}\n'
        )

        self.assertEqual(
            decode_response_text(response),
            '[{"a": "$@1"}, {"error": {"success": false, "message": "failed", "description": "already done"}}]',
        )

    def test_returns_empty_string_when_body_read_times_out(self) -> None:
        response = FakeResponse(delay_seconds=1)

        self.assertEqual(decode_response_text(response, timeout_seconds=0.05), "")


if __name__ == "__main__":
    unittest.main()
