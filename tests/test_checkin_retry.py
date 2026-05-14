import unittest
from unittest.mock import MagicMock, Mock, patch

from scripts.checkin import (
    AccountConfig,
    CheckinResult,
    ResponseBodyReadResult,
    build_telegram_message,
    choose_retry_delay,
    confirm_checkin_from_points_records,
    extract_today_checkin_remark,
    perform_checkin,
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


def make_result_with_attempt(response_success, attempt: int):
    result = make_result(response_success)
    result.attempt = attempt
    return result


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
        unknown = make_result_with_attempt(None, 1)
        definitive_failure = make_result_with_attempt(False, 2)
        browser = Mock()
        context = Mock()
        page = Mock()

        with (
            patch("scripts.checkin.MAX_CHECKIN_ATTEMPTS", 3),
            patch("scripts.checkin.RETRY_BASE_DELAY_SECONDS", 0),
            patch("scripts.checkin.time.sleep") as sleep,
            patch("scripts.checkin.create_logged_in_session", return_value=(context, page)),
            patch("scripts.checkin.prepare_retry_page", return_value=True),
            patch("scripts.checkin.execute_attempt", Mock(side_effect=[unknown, definitive_failure])) as execute_attempt,
            patch("scripts.checkin.close_session"),
        ):
            result = run_account_with_retries(browser, account)

        self.assertIs(result, definitive_failure)
        self.assertEqual(execute_attempt.call_count, 2)
        sleep.assert_not_called()

    def test_run_account_with_retries_reuses_existing_session(self) -> None:
        account = AccountConfig(username="user@example.com", password="secret", sign_type="gamble")
        unknown = make_result_with_attempt(None, 1)
        definitive_failure = make_result_with_attempt(False, 2)
        browser = Mock()
        context = Mock()
        page = Mock()

        with (
            patch("scripts.checkin.MAX_CHECKIN_ATTEMPTS", 3),
            patch("scripts.checkin.RETRY_BASE_DELAY_SECONDS", 0),
            patch("scripts.checkin.time.sleep"),
            patch("scripts.checkin.create_logged_in_session", return_value=(context, page)) as create_session,
            patch("scripts.checkin.prepare_retry_page", return_value=True) as prepare_retry_page,
            patch("scripts.checkin.execute_attempt", side_effect=[unknown, definitive_failure]) as execute_attempt,
            patch("scripts.checkin.close_session") as close_session,
        ):
            result = run_account_with_retries(browser, account)

        self.assertIs(result, definitive_failure)
        create_session.assert_called_once_with(browser, account, 1)
        prepare_retry_page.assert_called_once_with(page, 2)
        self.assertEqual(execute_attempt.call_count, 2)
        close_session.assert_called_once_with(context, 2)

    def test_run_account_with_retries_recreates_session_when_refresh_fails(self) -> None:
        account = AccountConfig(username="user@example.com", password="secret", sign_type="gamble")
        unknown = make_result_with_attempt(None, 1)
        definitive_failure = make_result_with_attempt(False, 2)
        browser = Mock()
        context1 = Mock()
        page1 = Mock()
        context2 = Mock()
        page2 = Mock()

        with (
            patch("scripts.checkin.MAX_CHECKIN_ATTEMPTS", 3),
            patch("scripts.checkin.RETRY_BASE_DELAY_SECONDS", 0),
            patch("scripts.checkin.time.sleep"),
            patch(
                "scripts.checkin.create_logged_in_session",
                side_effect=[(context1, page1), (context2, page2)],
            ) as create_session,
            patch("scripts.checkin.prepare_retry_page", return_value=False) as prepare_retry_page,
            patch("scripts.checkin.execute_attempt", side_effect=[unknown, definitive_failure]) as execute_attempt,
            patch("scripts.checkin.close_session") as close_session,
        ):
            result = run_account_with_retries(browser, account)

        self.assertIs(result, definitive_failure)
        self.assertEqual(create_session.call_count, 2)
        prepare_retry_page.assert_called_once_with(page1, 2)
        close_session.assert_any_call(context1, 2)
        close_session.assert_any_call(context2, 2)
        self.assertEqual(execute_attempt.call_count, 2)

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

    def test_extract_today_checkin_remark_handles_wrapped_mobile_rows(self) -> None:
        body_text = """
        积分记录
        类型
        积分
        备注
        创建时间
        分享奖励
        +4
        用户解锁
        了资源 维
        多利亚一
        号 (2010)
        获得积分
        4
        2026-05-
        14 10:15
        签到
        0
        签到成
        功，获得
        0 积分
        2026-05-
        14 07:29
        解锁资源
        -4
        解锁资源
        爱情抓马
        (2026) 扣
        除积分 4
        2026-05-
        13 09:53
        """

        remark = extract_today_checkin_remark(body_text, target_date="2026-05-14")

        self.assertEqual(remark, "签到成功，获得 0 积分")

    def test_confirm_points_records_reopens_user_menu_before_navigation(self) -> None:
        page = Mock()
        body = Mock()
        page.locator.return_value = body
        body.inner_text.return_value = (
            "积分记录\n类型\n积分\n备注\n创建时间\n签到\n+16\n签到成功，获得 16 积分\n2026-05-10 06:04"
        )

        with (
            patch("scripts.checkin.open_user_menu", return_value=True) as open_menu,
            patch("scripts.checkin.click_menu_entry", side_effect=[True, True]) as click_menu_entry,
            patch("scripts.checkin.extract_today_checkin_remark", return_value="签到成功，获得 16 积分"),
        ):
            remark = confirm_checkin_from_points_records(page, attempt=2)

        self.assertEqual(remark, "签到成功，获得 16 积分")
        open_menu.assert_called_once_with(page, quiet=True)
        click_menu_entry.assert_any_call(page, "个人中心", timeout_ms=5_000)
        click_menu_entry.assert_any_call(page, "积分记录", timeout_ms=5_000)
        page.wait_for_timeout.assert_any_call(2_000)

    def test_confirm_points_records_refreshes_before_navigation(self) -> None:
        page = Mock()
        body = Mock()
        page.locator.return_value = body
        body.inner_text.return_value = (
            "积分记录\n类型\n积分\n备注\n创建时间\n签到\n+16\n签到成功，获得 16 积分\n2026-05-10 06:04"
        )

        with (
            patch("scripts.checkin.dismiss_notice") as dismiss_notice,
            patch("scripts.checkin.open_user_menu", return_value=True),
            patch("scripts.checkin.click_menu_entry", side_effect=[True, True]),
            patch("scripts.checkin.extract_today_checkin_remark", return_value="签到成功，获得 16 积分"),
        ):
            remark = confirm_checkin_from_points_records(page, attempt=2)

        self.assertEqual(remark, "签到成功，获得 16 积分")
        page.goto.assert_called_once()
        dismiss_notice.assert_called_once_with(page)
        self.assertGreaterEqual(page.wait_for_timeout.call_count, 3)

    def test_confirm_points_records_clicks_points_record_again_when_body_is_still_personal_center(self) -> None:
        page = Mock()
        points_record_body = (
            "积分记录\n类型\n积分\n备注\n创建时间\n签到\n+16\n签到成功，获得 16 积分\n2026-05-10 06:04"
        )

        with (
            patch("scripts.checkin.open_user_menu", return_value=True),
            patch("scripts.checkin.click_menu_entry", side_effect=[True, True, True]) as click_menu_entry,
            patch("scripts.checkin.wait_for_points_record_body", side_effect=[None, points_record_body]),
            patch("scripts.checkin.extract_today_checkin_remark", return_value="签到成功，获得 16 积分"),
        ):
            remark = confirm_checkin_from_points_records(page, attempt=2)

        self.assertEqual(remark, "签到成功，获得 16 积分")
        self.assertEqual(click_menu_entry.call_count, 3)
        click_menu_entry.assert_any_call(page, "积分记录", timeout_ms=5_000)

    def test_telegram_message_distinguishes_result_source(self) -> None:
        from_response = CheckinResult(
            username="a@example.com",
            sign_type="gamble",
            sign_label="赌狗签到",
            status="success",
            response_success=True,
            message="签到成功",
            description="获得 12 积分",
            result_source="response",
        )
        from_points = CheckinResult(
            username="b@example.com",
            sign_type="gamble",
            sign_label="赌狗签到",
            status="success",
            response_success=True,
            message="",
            description="签到成功，获得 16 积分",
            result_source="points_record",
        )

        message = build_telegram_message([from_response, from_points])

        self.assertIn("来源：<code>接口响应</code>", message)
        self.assertIn("来源：<code>积分记录核验</code>", message)

    def test_perform_checkin_prefers_points_record_after_already_signed_response(self) -> None:
        account = AccountConfig(username="user@example.com", password="secret", sign_type="gamble")
        page = Mock()
        response_context = MagicMock()
        response_context.__enter__.return_value.value = Mock()
        page.expect_response.return_value = response_context
        response = Mock()
        response.status = 200
        response.request.headers = {"next-action": "token"}
        body_result = ResponseBodyReadResult(
            decoded_text='{"error":{"success":false,"message":"签到失败","description":"你已经签到过了，明天再来吧"}}',
            raw_text_preview="preview",
            raw_bytes_len=10,
            read_status="ok",
        )
        item = Mock()

        with (
            patch("scripts.checkin.menu_sign_item", return_value=item),
            patch("scripts.checkin.select_action_response", return_value=(response, body_result, False, "签到失败", "你已经签到过了，明天再来吧")),
            patch("scripts.checkin.confirm_checkin_from_points_records", return_value="签到成功，获得 16 积分"),
        ):
            result = perform_checkin(page, account, attempt=2)

        self.assertEqual(result.status, "success")
        self.assertTrue(result.response_success)
        self.assertEqual(result.description, "签到成功，获得 16 积分")
        self.assertEqual(result.result_source, "points_record")

    def test_perform_checkin_retries_when_already_signed_cannot_be_confirmed(self) -> None:
        account = AccountConfig(username="user@example.com", password="secret", sign_type="gamble")
        page = Mock()
        response_context = MagicMock()
        response_context.__enter__.return_value.value = Mock()
        page.expect_response.return_value = response_context
        response = Mock()
        response.status = 200
        response.request.headers = {"next-action": "token"}
        body_result = ResponseBodyReadResult(
            decoded_text='{"error":{"success":false,"message":"签到失败","description":"你已经签到过了，明天再来吧"}}',
            raw_text_preview="preview",
            raw_bytes_len=10,
            read_status="ok",
        )
        item = Mock()

        with (
            patch("scripts.checkin.menu_sign_item", return_value=item),
            patch("scripts.checkin.select_action_response", return_value=(response, body_result, False, "签到失败", "你已经签到过了，明天再来吧")),
            patch("scripts.checkin.confirm_checkin_from_points_records", return_value=None),
        ):
            result = perform_checkin(page, account, attempt=2)

        self.assertEqual(result.status, "unknown")
        self.assertIsNone(result.response_success)
        self.assertEqual(result.result_source, "")


if __name__ == "__main__":
    unittest.main()
