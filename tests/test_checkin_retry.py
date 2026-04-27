import unittest
from unittest.mock import Mock, patch

from scripts.checkin import (
    AccountConfig,
    CheckinResult,
    choose_retry_delay,
    run_account_with_retries,
    should_retry_result,
)


def make_result(response_success):
    return CheckinResult(
        username="user@example.com",
        sign_type="gamble",
        sign_label="赌狗签到",
        status="unknown" if response_success is None else "failed",
        response_success=response_success,
        message="message",
        description="description",
    )


class CheckinRetryTest(unittest.TestCase):
    def test_retries_only_unknown_results(self) -> None:
        self.assertTrue(should_retry_result(make_result(None)))
        self.assertFalse(should_retry_result(make_result(False)))
        self.assertFalse(should_retry_result(make_result(True)))

    def test_retry_delay_uses_linear_backoff(self) -> None:
        self.assertEqual(choose_retry_delay(1, base_delay_seconds=3), 3)
        self.assertEqual(choose_retry_delay(2, base_delay_seconds=3), 6)
        self.assertEqual(choose_retry_delay(3, base_delay_seconds=3), 9)

    def test_run_account_with_retries_stops_after_definitive_result(self) -> None:
        account = AccountConfig(username="user@example.com", password="secret", sign_type="gamble")
        unknown = make_result(None)
        definitive_failure = make_result(False)

        with (
            patch("scripts.checkin.MAX_CHECKIN_ATTEMPTS", 3),
            patch("scripts.checkin.RETRY_BASE_DELAY_SECONDS", 0),
            patch("scripts.checkin.time.sleep") as sleep,
            patch("scripts.checkin.run_account_once", Mock(side_effect=[unknown, definitive_failure])) as run_once,
        ):
            result = run_account_with_retries(Mock(), account)

        self.assertIs(result, definitive_failure)
        self.assertEqual(run_once.call_count, 2)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
