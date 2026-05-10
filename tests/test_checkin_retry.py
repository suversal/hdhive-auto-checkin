import unittest
from unittest.mock import Mock, patch

from scripts.checkin import (
    AccountConfig,
    CheckinResult,
    choose_retry_delay,
    confirm_checkin_from_points_records,
    extract_today_checkin_remark,
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

    def test_extract_today_checkin_remark_skips_non_checkin_records(self) -> None:
        body_text = """
        积分记录
        类型
        积分
        备注
        创建时间
        系统奖励
        +100
        不妨陪妈妈看一部她喜欢的电影或者电视剧
        2026-05-10 12:13
        签到
        +16
        签到成功，获得 16 积分
        2026-05-10 06:04
        签到
        +15
        签到成功，获得 15 积分
        2026-05-09 06:14
        """

        remark = extract_today_checkin_remark(body_text, target_date="2026-05-10")

        self.assertEqual(remark, "签到成功，获得 16 积分")

    def test_extract_today_checkin_remark_returns_none_when_missing(self) -> None:
        body_text = """
        积分记录
        系统奖励
        +100
        测试奖励
        2026-05-10 12:13
        签到
        +15
        签到成功，获得 15 积分
        2026-05-09 06:14
        """

        self.assertIsNone(extract_today_checkin_remark(body_text, target_date="2026-05-10"))

    def test_confirm_points_records_reopens_user_menu_before_navigation(self) -> None:
        page = Mock()
        body = Mock()
        page.locator.return_value = body
        body.inner_text.return_value = "积分记录\n签到成功，获得 16 积分\n2026-05-10 06:04"
        points_title = Mock()
        page.get_by_text.return_value.first = points_title

        with (
            patch("scripts.checkin.open_user_menu", return_value=True) as open_menu,
            patch("scripts.checkin.click_first_visible", side_effect=[True, True]) as click_visible,
            patch("scripts.checkin.extract_today_checkin_remark", return_value="签到成功，获得 16 积分"),
        ):
            remark = confirm_checkin_from_points_records(page, attempt=2)

        self.assertEqual(remark, "签到成功，获得 16 积分")
        open_menu.assert_called_once_with(page, quiet=True)
        self.assertEqual(click_visible.call_count, 2)
        page.wait_for_timeout.assert_any_call(2_000)
        points_title.wait_for.assert_called_once()


if __name__ == "__main__":
    unittest.main()
