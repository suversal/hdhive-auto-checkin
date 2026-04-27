import time
import unittest
from typing import Optional

from scripts.checkin import decode_response_text, read_response_body_result


class FakeResponse:
    def __init__(
        self,
        body_bytes: bytes = b"",
        delay_seconds: float = 0,
        body_exception: Optional[Exception] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        self.body_bytes = body_bytes
        self.delay_seconds = delay_seconds
        self.body_exception = body_exception
        self.headers = headers or {}

    def body(self) -> bytes:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if self.body_exception is not None:
            raise self.body_exception
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

    def test_marks_timeout_status_when_body_read_times_out(self) -> None:
        response = FakeResponse(delay_seconds=1, headers={"content-type": "text/x-component"})

        result = read_response_body_result(response, timeout_seconds=0.05)

        self.assertEqual(result.read_status, "timeout")
        self.assertEqual(result.header_content_type, "text/x-component")
        self.assertEqual(result.decoded_text, "")

    def test_marks_exception_status_when_body_read_raises(self) -> None:
        response = FakeResponse(body_exception=RuntimeError("stream closed"))

        result = read_response_body_result(response)

        self.assertEqual(result.read_status, "exception")
        self.assertEqual(result.exception_type, "RuntimeError")
        self.assertEqual(result.exception_message, "stream closed")
        self.assertEqual(result.decoded_text, "")


if __name__ == "__main__":
    unittest.main()
