import json
import unittest
from unittest.mock import Mock, patch

from scripts.checkin import (
    AccountConfig,
    CheckinResult,
    CaptchaClickPoint,
    ResponseBodyReadResult,
    SpaceClickChallenge,
    build_telegram_message,
    capture_space_click_challenge_display_image,
    choose_retry_delay,
    clear_notice_before_captcha_action,
    confirm_checkin_from_points_records,
    create_yescaptcha_space_click_task,
    create_yescaptcha_turnstile_task,
    extract_action_fields,
    extract_today_checkin_remark,
    is_captcha_required_response,
    parse_yescaptcha_click_points,
    perform_checkin,
    request_yescaptcha_space_click_points,
    request_yescaptcha_turnstile_token,
    normalize_space_click_prompt,
    refresh_expired_space_click_challenge,
    run_account_with_retries,
    should_retry_result,
    space_click_challenge_visible,
    space_click_display_position,
    space_click_needs_retry_message,
    wait_for_checkin_action_response,
    click_menu_entry,
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
    def test_create_yescaptcha_turnstile_task_posts_documented_payload(self) -> None:
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"errorId":0,"taskId":"task-123"}'

        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        with patch("scripts.checkin.urlopen", side_effect=fake_urlopen):
            task_id = create_yescaptcha_turnstile_task(
                client_key="client-key",
                website_url="https://hdhive.com",
                website_key="0x4AAAA",
            )

        self.assertEqual(task_id, "task-123")
        request = captured["request"]
        self.assertEqual(request.full_url, "https://api.yescaptcha.com/createTask")
        self.assertEqual(request.get_method(), "POST")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["clientKey"], "client-key")
        self.assertEqual(
            payload["task"],
            {
                "type": "TurnstileTaskProxyless",
                "websiteURL": "https://hdhive.com",
                "websiteKey": "0x4AAAA",
            },
        )

    def test_create_yescaptcha_space_click_task_posts_image_prompt_payload(self) -> None:
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"errorId":0,"status":"ready","solution":{"box":["120","80"]}}'

        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        challenge = SpaceClickChallenge(
            prompt="请点击大型黄色物品。",
            image_base64="base64-image",
            image_width=344,
            image_height=344,
            display_width=344,
            display_height=344,
        )

        with patch("scripts.checkin.urlopen", side_effect=fake_urlopen):
            result = create_yescaptcha_space_click_task("client-key", challenge)

        self.assertEqual(result["solution"]["box"], ["120", "80"])
        request = captured["request"]
        self.assertEqual(request.full_url, "https://api.yescaptcha.com/createTask")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["clientKey"], "client-key")
        self.assertEqual(payload["task"]["type"], "HCaptchaClassification")
        self.assertEqual(payload["task"]["queries"], ["base64-image"])
        self.assertEqual(payload["task"]["question"], "Click the large yellow object.")

    def test_normalize_space_click_prompt_translates_spatial_relation(self) -> None:
        self.assertEqual(
            normalize_space_click_prompt("请点击在灰色多面体后面的立方体。"),
            "Click the cube behind the gray polyhedron.",
        )
        self.assertEqual(
            normalize_space_click_prompt("请点击与绿色圆柱体有相同大小的圆锥。"),
            "Click the cone with the same size as the green cylinder.",
        )
        self.assertEqual(
            normalize_space_click_prompt("请点击在小型正方体后面的物品。"),
            "Click the object behind the small cube.",
        )
        self.assertEqual(
            normalize_space_click_prompt("请点击与蓝色物体有相同形状的物体。"),
            "Click the object with the same shape as the blue object.",
        )
        self.assertEqual(
            normalize_space_click_prompt("请点击大尺寸灰色物体。"),
            "Click the large gray object.",
        )

    def test_request_yescaptcha_turnstile_token_polls_until_ready(self) -> None:
        responses = [
            b'{"errorId":0,"taskId":"task-123"}',
            b'{"errorId":0,"status":"processing"}',
            b'{"errorId":0,"status":"ready","solution":{"token":"cf-token"}}',
        ]

        class FakeResponse:
            status = 200

            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return self.body

        with (
            patch("scripts.checkin.urlopen", side_effect=[FakeResponse(body) for body in responses]),
            patch("scripts.checkin.time.sleep") as sleep,
        ):
            token = request_yescaptcha_turnstile_token(
                client_key="client-key",
                website_url="https://hdhive.com",
                website_key="0x4AAAA",
            )

        self.assertEqual(token, "cf-token")
        sleep.assert_called_once()

    def test_request_yescaptcha_space_click_points_polls_until_ready(self) -> None:
        responses = [
            b'{"errorId":0,"taskId":"task-456"}',
            b'{"errorId":0,"status":"processing"}',
            b'{"errorId":0,"status":"ready","solution":{"box":["120","80","240","160"]}}',
        ]

        class FakeResponse:
            status = 200

            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return self.body

        challenge = SpaceClickChallenge(
            prompt="请点击大型黄色物品。",
            image_base64="base64-image",
            image_width=344,
            image_height=344,
            display_width=344,
            display_height=344,
        )

        with (
            patch("scripts.checkin.urlopen", side_effect=[FakeResponse(body) for body in responses]),
            patch("scripts.checkin.time.sleep") as sleep,
        ):
            points = request_yescaptcha_space_click_points("client-key", challenge)

        self.assertEqual(points, [CaptchaClickPoint(120, 80), CaptchaClickPoint(240, 160)])
        sleep.assert_called_once()

    def test_parse_yescaptcha_click_points_accepts_nested_and_dict_formats(self) -> None:
        self.assertEqual(
            parse_yescaptcha_click_points({"box": [["120", "80"], {"x": 240, "y": 160}]}),
            [CaptchaClickPoint(120, 80), CaptchaClickPoint(240, 160)],
        )

    def test_space_click_display_position_scales_from_uploaded_image_coordinates(self) -> None:
        challenge = SpaceClickChallenge(
            prompt="请点击目标",
            image_base64="base64-image",
            image_width=344,
            image_height=344,
            display_width=414,
            display_height=187,
            image_offset_x=12,
            image_offset_y=8,
        )

        x, y = space_click_display_position(challenge, CaptchaClickPoint(86, 172))

        self.assertAlmostEqual(x, 12 + 86 * 414 / 344)
        self.assertAlmostEqual(y, 8 + 172 * 187 / 344)

    def test_capture_space_click_challenge_display_image_uses_visible_clip(self) -> None:
        page = Mock()
        page.screenshot.return_value = b"visible-image"
        challenge = SpaceClickChallenge(
            prompt="请点击目标",
            image_base64="original-image",
            image_width=344,
            image_height=344,
            display_width=414,
            display_height=187,
            image_offset_x=12,
            image_offset_y=8,
            image_viewport_x=50,
            image_viewport_y=80,
        )

        updated = capture_space_click_challenge_display_image(page, challenge)

        self.assertEqual(updated.image_base64, "dmlzaWJsZS1pbWFnZQ==")
        self.assertEqual(updated.image_width, 414)
        self.assertEqual(updated.image_height, 187)
        self.assertEqual(updated.display_width, 414)
        self.assertEqual(updated.display_height, 187)
        page.screenshot.assert_called_once_with(
            type="jpeg",
            quality=92,
            scale="css",
            clip={"x": 50, "y": 80, "width": 414, "height": 187},
        )

    def test_refresh_expired_space_click_challenge_waits_after_refresh_click(self) -> None:
        page = Mock()
        page.evaluate.return_value = True

        refreshed = refresh_expired_space_click_challenge(page)

        self.assertTrue(refreshed)
        page.wait_for_timeout.assert_called_once_with(1_500)

    def test_space_click_retry_message_detects_incorrect_position_prompt(self) -> None:
        self.assertTrue(space_click_needs_retry_message("点击位置不正确，请重试"))
        self.assertTrue(space_click_needs_retry_message("验证码无效或已过期"))
        self.assertFalse(space_click_needs_retry_message("请点击绿色圆柱体"))

    def test_clear_notice_before_captcha_action_closes_late_notice_until_stable(self) -> None:
        page = Mock()

        with patch("scripts.checkin.dismiss_notice", side_effect=[True, False]) as dismiss_notice:
            clear_notice_before_captcha_action(page, wait_for_appearance_ms=12_000)

        self.assertEqual(dismiss_notice.call_count, 2)
        dismiss_notice.assert_any_call(page, wait_for_appearance_ms=12_000)
        dismiss_notice.assert_any_call(page, wait_for_appearance_ms=1_000)

    def test_wait_for_checkin_action_response_fails_fast_after_space_click_limit(self) -> None:
        page = Mock()

        with (
            patch("scripts.checkin.YESCAPTCHA_SPACE_MAX_SOLVES", 1),
            patch("scripts.checkin.solve_space_click_challenge_if_present", return_value=True),
            patch("scripts.checkin.solve_turnstile_challenge_if_present", return_value=False),
            patch("scripts.checkin.space_click_challenge_visible", return_value=True),
        ):
            with self.assertRaisesRegex(Exception, "点选验证码处理次数已达上限"):
                wait_for_checkin_action_response(page, [], attempt=1, timeout_ms=1_000)

    def test_extract_action_fields_ignores_unrelated_page_success_fields(self) -> None:
        text = json.dumps(
            [
                {"success": True, "title": "unrelated page payload"},
                {"success": True, "description": "movie description from page payload"},
                {
                    "error": {
                        "success": False,
                        "message": "当前环境需要完成验证码验证",
                        "description": "当前操作需要完成验证码验证后继续",
                        "code": "400401",
                    }
                },
            ],
            ensure_ascii=False,
        )

        success, message, description = extract_action_fields(text)

        self.assertFalse(success)
        self.assertEqual(message, "当前环境需要完成验证码验证")
        self.assertEqual(description, "当前操作需要完成验证码验证后继续")

    def test_is_captcha_required_response_detects_challenge_error(self) -> None:
        self.assertTrue(
            is_captcha_required_response(
                False,
                "当前环境需要完成验证码验证",
                "当前操作需要完成验证码验证后继续",
                '{"challenge_type":"slider_captcha","code":"400401"}',
            )
        )

    def test_extract_action_fields_keeps_business_error_when_later_chunks_have_success(self) -> None:
        text = json.dumps(
            [
                {
                    "error": {
                        "success": False,
                        "message": "签到失败",
                        "description": "你已经签到过了，明天再来吧",
                    }
                },
                {"response": {"success": True}},
            ],
            ensure_ascii=False,
        )

        success, message, description = extract_action_fields(text)

        self.assertFalse(success)
        self.assertEqual(message, "签到失败")
        self.assertEqual(description, "你已经签到过了，明天再来吧")

    def test_wait_for_checkin_action_response_solves_turnstile_before_response(self) -> None:
        page = Mock()
        response = Mock()
        action_responses = []

        def wait_for_timeout(_timeout_ms):
            if not action_responses:
                action_responses.append(response)

        page.wait_for_timeout.side_effect = wait_for_timeout

        with patch("scripts.checkin.solve_turnstile_challenge_if_present", return_value=True) as solve:
            result = wait_for_checkin_action_response(page, action_responses, attempt=1, timeout_ms=5_000)

        self.assertIs(result, response)
        solve.assert_called_once_with(page, 1)

    def test_wait_for_checkin_action_response_solves_space_click_before_response(self) -> None:
        page = Mock()
        response = Mock()
        action_responses = []

        def solve_space(_page, _attempt):
            if not action_responses:
                action_responses.append(response)
            return True

        with (
            patch("scripts.checkin.solve_space_click_challenge_if_present", side_effect=solve_space) as solve_space_click,
            patch("scripts.checkin.solve_turnstile_challenge_if_present") as solve_turnstile,
        ):
            result = wait_for_checkin_action_response(page, action_responses, attempt=1, timeout_ms=5_000)

        self.assertIs(result, response)
        solve_space_click.assert_called_once_with(page, 1)
        solve_turnstile.assert_not_called()

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

    def test_click_menu_entry_falls_back_to_dom_text_click(self) -> None:
        page = Mock()
        hidden_locator = Mock()
        hidden_locator.count.return_value = 0
        page.get_by_role.return_value = hidden_locator
        page.get_by_text.return_value = hidden_locator
        page.evaluate.return_value = True

        self.assertTrue(click_menu_entry(page, "积分记录"))
        page.evaluate.assert_called_once()

    def test_click_menu_entry_waits_for_late_rendered_dom_text(self) -> None:
        page = Mock()
        hidden_locator = Mock()
        hidden_locator.count.return_value = 0
        page.get_by_role.return_value = hidden_locator
        page.get_by_text.return_value = hidden_locator
        page.evaluate.side_effect = [False, True]

        self.assertTrue(click_menu_entry(page, "积分记录", timeout_ms=1_000))
        self.assertEqual(page.evaluate.call_count, 2)
        page.wait_for_timeout.assert_called_once_with(300)

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
        response = Mock()
        response.status = 200
        response.request.headers = {"next-action": "token"}
        body_result = ResponseBodyReadResult(
            decoded_text='{"error":{"success":false,"message":"签到失败","description":"你已经签到过了，明天再来吧"}}',
            raw_text_preview="preview",
            raw_bytes_len=10,
            read_status="ok",
        )
        with (
            patch("scripts.checkin.open_user_menu", return_value=True),
            patch("scripts.checkin.click_menu_entry", return_value=True),
            patch("scripts.checkin.SIGN_CLICK_DELAY_SECONDS", 1.25),
            patch("scripts.checkin.wait_for_checkin_action_response", return_value=response),
            patch("scripts.checkin.select_action_response", return_value=(response, body_result, False, "签到失败", "你已经签到过了，明天再来吧")),
            patch("scripts.checkin.confirm_checkin_from_points_records", return_value="签到成功，获得 16 积分"),
        ):
            result = perform_checkin(page, account, attempt=2)

        self.assertEqual(result.status, "success")
        self.assertTrue(result.response_success)
        self.assertEqual(result.description, "签到成功，获得 16 积分")
        self.assertEqual(result.result_source, "points_record")
        page.wait_for_timeout.assert_any_call(1_250)

    def test_perform_checkin_retries_when_already_signed_cannot_be_confirmed(self) -> None:
        account = AccountConfig(username="user@example.com", password="secret", sign_type="gamble")
        page = Mock()
        response = Mock()
        response.status = 200
        response.request.headers = {"next-action": "token"}
        body_result = ResponseBodyReadResult(
            decoded_text='{"error":{"success":false,"message":"签到失败","description":"你已经签到过了，明天再来吧"}}',
            raw_text_preview="preview",
            raw_bytes_len=10,
            read_status="ok",
        )
        with (
            patch("scripts.checkin.open_user_menu", return_value=True),
            patch("scripts.checkin.click_menu_entry", return_value=True),
            patch("scripts.checkin.wait_for_checkin_action_response", return_value=response),
            patch("scripts.checkin.select_action_response", return_value=(response, body_result, False, "签到失败", "你已经签到过了，明天再来吧")),
            patch("scripts.checkin.confirm_checkin_from_points_records", return_value=None),
        ):
            result = perform_checkin(page, account, attempt=2)

        self.assertEqual(result.status, "unknown")
        self.assertIsNone(result.response_success)
        self.assertEqual(result.result_source, "")

    def test_perform_checkin_continues_after_captcha_required_response(self) -> None:
        account = AccountConfig(username="user@example.com", password="secret", sign_type="gamble")
        page = Mock()
        challenge_response = Mock()
        challenge_response.status = 200
        challenge_response.request.headers = {"next-action": "token"}
        success_response = Mock()
        success_response.status = 200
        success_response.request.headers = {"next-action": "token"}
        challenge_body = ResponseBodyReadResult(
            decoded_text='{"error":{"success":false,"message":"当前环境需要完成验证码验证","description":"当前操作需要完成验证码验证后继续","code":"400401"}}',
            raw_text_preview="challenge",
            raw_bytes_len=10,
            read_status="ok",
        )
        success_body = ResponseBodyReadResult(
            decoded_text='{"response":{"success":true,"message":"","description":"获得 20 积分"}}',
            raw_text_preview="success",
            raw_bytes_len=10,
            read_status="ok",
        )

        with (
            patch("scripts.checkin.open_user_menu", return_value=True),
            patch("scripts.checkin.click_menu_entry", return_value=True),
            patch("scripts.checkin.wait_for_checkin_action_response", return_value=challenge_response),
            patch(
                "scripts.checkin.select_action_response",
                side_effect=[
                    (challenge_response, challenge_body, False, "当前环境需要完成验证码验证", "当前操作需要完成验证码验证后继续"),
                    (success_response, success_body, True, "", "获得 20 积分"),
                ],
            ),
            patch("scripts.checkin.wait_for_challenge_followup_responses", return_value=[success_response]) as wait_followup,
        ):
            result = perform_checkin(page, account, attempt=1)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.description, "获得 20 积分")
        wait_followup.assert_called_once_with(page, 1)


if __name__ == "__main__":
    unittest.main()
