import unittest
from unittest.mock import AsyncMock, Mock
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs

from scripts.telegram_checkin import (
    build_markdown_summary,
    build_summary_message,
    build_run_summary,
    build_summary_notification_message,
    TelegramRuntimeConfig,
    TelegramCheckinResult,
    load_account_configs_from_mapping,
    load_telegram_bot_token_from_mapping,
    load_summary_notify_chat_id_from_mapping,
    resolve_notify_target,
    send_run_summary_notification,
    send_summary_notification,
    parse_bot_reply,
    write_outputs,
)
from scripts.generate_telegram_session import build_session_output, validate_api_credentials


class TelegramReplyParsingTest(unittest.IsolatedAsyncioTestCase):
    def test_parses_success_with_points(self) -> None:
        result = parse_bot_reply("🎰 签到成功，获得 16 积分", command="赌狗签到")

        self.assertEqual(result.status, "success")
        self.assertTrue(result.response_success)
        self.assertEqual(result.points, 16)
        self.assertFalse(result.already_signed)
        self.assertEqual(result.description, "🎰 签到成功，获得 16 积分")

    def test_parses_success_with_zero_points(self) -> None:
        result = parse_bot_reply("🎰 签到成功，获得 0 积分", command="赌狗签到")

        self.assertEqual(result.status, "success")
        self.assertTrue(result.response_success)
        self.assertEqual(result.points, 0)

    def test_treats_already_signed_as_success(self) -> None:
        result = parse_bot_reply("你已经签到过了，明天再来吧", command="赌狗签到")

        self.assertEqual(result.status, "success")
        self.assertTrue(result.response_success)
        self.assertTrue(result.already_signed)
        self.assertIsNone(result.points)
        self.assertEqual(result.description, "你已经签到过了，明天再来吧")

    def test_parses_explicit_failure(self) -> None:
        result = parse_bot_reply("签到失败，请稍后再试", command="赌狗签到")

        self.assertEqual(result.status, "failed")
        self.assertFalse(result.response_success)
        self.assertEqual(result.description, "签到失败，请稍后再试")

    def test_unknown_reply_keeps_raw_text(self) -> None:
        result = parse_bot_reply("当前服务繁忙", command="赌狗签到")

        self.assertEqual(result.status, "unknown")
        self.assertIsNone(result.response_success)
        self.assertEqual(result.description, "当前服务繁忙")

    def test_summary_marks_already_signed_successfully(self) -> None:
        result = parse_bot_reply("你已经签到过了，明天再来吧", command="赌狗签到")

        message = build_summary_message(result)

        self.assertIn("状态: <b>签到成功</b>", message)
        self.assertIn("已签: <code>是</code>", message)
        self.assertIn("你已经签到过了，明天再来吧", message)

    def test_summary_escapes_html_reply_text(self) -> None:
        result = parse_bot_reply("签到失败 <retry>", command="赌狗签到")

        message = build_summary_message(result)

        self.assertIn("签到失败 &lt;retry&gt;", message)
        self.assertNotIn("签到失败 <retry>", message)

    def test_markdown_summary_contains_points(self) -> None:
        result = parse_bot_reply("🎰 签到成功，获得 16 积分", command="赌狗签到")

        summary = build_markdown_summary(result)

        self.assertIn("- Success: `1`", summary)
        self.assertIn("| default | `赌狗签到` | `success` | `False` | `16` |", summary)

    def test_write_outputs_saves_latest_results_json(self) -> None:
        result = parse_bot_reply("🎰 签到成功，获得 16 积分", command="赌狗签到")

        with TemporaryDirectory() as temp_dir:
            write_outputs(result, Path(temp_dir))
            saved = Path(temp_dir, "latest-results.json").read_text(encoding="utf-8")

        self.assertIn('"status": "success"', saved)
        self.assertIn('"points": 16', saved)

    def test_load_account_configs_from_accounts_json(self) -> None:
        configs = load_account_configs_from_mapping(
            {
                "telegram_api_id": "123",
                "telegram_api_hash": "hash",
                "telegram_response_timeout_seconds": "30",
                "hdhive_telegram_accounts_json": """
                [
                  {"name": "account-a", "session": "session-a", "bot_username": "@bot_a"},
                  {"name": "account-b", "session": "session-b", "bot_username": "@bot_b", "command": "签到", "notify_chat_id": ""}
                ]
                """,
            }
        )

        self.assertEqual(len(configs), 2)
        self.assertEqual(configs[0].name, "account-a")
        self.assertEqual(configs[0].command, "赌狗签到")
        self.assertEqual(configs[0].notify_chat_id, "")
        self.assertEqual(configs[1].name, "account-b")
        self.assertEqual(configs[1].command, "签到")
        self.assertEqual(configs[1].notify_chat_id, "")

    def test_load_summary_notify_chat_id_is_separate_from_account_notify_targets(self) -> None:
        mapping = {
            "telegram_summary_notify_chat_id": "main",
        }

        self.assertEqual(load_summary_notify_chat_id_from_mapping(mapping), "main")

    def test_load_telegram_bot_token_from_mapping(self) -> None:
        mapping = {
            "telegram_bot_token": "bot-token",
        }

        self.assertEqual(load_telegram_bot_token_from_mapping(mapping), "bot-token")

    def test_build_summary_notification_message_lists_all_accounts(self) -> None:
        results = [
            TelegramCheckinResult(
                account_name="account-a",
                command="赌狗签到",
                status="success",
                response_success=True,
                message="签到成功",
                description="签到成功，获得 1 积分",
                points=1,
            ),
            TelegramCheckinResult(
                account_name="account-b",
                command="赌狗签到",
                status="success",
                response_success=True,
                message="今日已签到",
                description="你已经签到过了，明天再来吧",
                already_signed=True,
            ),
        ]

        message = build_summary_notification_message(results)

        self.assertIn("🧩 <b>HDHive 自动签到</b>", message)
        self.assertIn("━━━━━━━━━━━━━━━━━━", message)
        self.assertIn("🌐 目标站点：<code>https://hdhive.com</code>", message)
        self.assertIn("📊 统计汇总：成功 2  /失败 0  /未知 0", message)
        self.assertIn("⎡ 📧 账号：<code>account-a</code>", message)
        self.assertIn("├ 🏷️ 类型：赌狗签到", message)
        self.assertIn("⎣ 📝 结果：签到成功，获得 1 积分", message)
        self.assertIn("⎡ 📧 账号：<code>account-b</code>", message)
        self.assertIn("⎣ 📝 结果：你已经签到过了，明天再来吧", message)

    def test_load_account_configs_accepts_local_list(self) -> None:
        configs = load_account_configs_from_mapping(
            {
                "telegram_api_id": "123",
                "telegram_api_hash": "hash",
                "hdhive_telegram_accounts_json": [
                    {"name": "account-a", "session": "session-a", "bot_username": "@bot_a"}
                ],
            }
        )

        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0].name, "account-a")
        self.assertEqual(configs[0].session, "session-a")

    def test_load_account_configs_requires_accounts_array(self) -> None:
        with self.assertRaisesRegex(Exception, "HDHIVE_TELEGRAM_ACCOUNTS_JSON"):
            load_account_configs_from_mapping(
                {
                    "telegram_api_id": "123",
                    "telegram_api_hash": "hash",
                    "telegram_session": "single-session",
                    "hdhive_bot_username": "@bot",
                }
            )

    def test_load_account_configs_uses_default_command_when_account_omits_it(self) -> None:
        configs = load_account_configs_from_mapping(
            {
                "telegram_api_id": "123",
                "telegram_api_hash": "hash",
                "hdhive_telegram_accounts_json": [
                    {"name": "account-a", "session": "session-a", "bot_username": "@bot_a"}
                ],
            }
        )

        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0].name, "account-a")
        self.assertEqual(configs[0].command, "赌狗签到")

    def test_build_run_summary_counts_multiple_results(self) -> None:
        results = [
            TelegramCheckinResult(
                account_name="a",
                command="赌狗签到",
                status="success",
                response_success=True,
                message="签到成功",
                description="签到成功，获得 1 积分",
            ),
            TelegramCheckinResult(
                account_name="b",
                command="赌狗签到",
                status="unknown",
                response_success=None,
                message="未识别机器人回复",
                description="当前服务繁忙",
            ),
        ]

        summary = build_run_summary(results)

        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["success"], 1)
        self.assertEqual(summary["unknown"], 1)

    def test_send_run_summary_notification_uses_telegram_bot_api(self) -> None:
        result = TelegramCheckinResult(
            account_name="account-a",
            command="赌狗签到",
            status="success",
            response_success=True,
            message="签到成功",
            description="签到成功，获得 1 积分",
            points=1,
        )
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"ok":true}'

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = request.data.decode("utf-8")
            return FakeResponse()

        with unittest.mock.patch("scripts.telegram_checkin.urlopen", side_effect=fake_urlopen):
            sent = send_run_summary_notification("bot-token", "123456", [result])

        self.assertTrue(sent)
        self.assertEqual(captured["url"], "https://api.telegram.org/botbot-token/sendMessage")
        self.assertEqual(captured["timeout"], 30)
        payload = parse_qs(captured["body"])
        self.assertEqual(payload["chat_id"], ["123456"])
        self.assertEqual(payload["parse_mode"], ["HTML"])
        self.assertIn("account-a", payload["text"][0])

    def test_validate_api_credentials_rejects_empty_values(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "API_ID"):
            validate_api_credentials(0, "hash")
        with self.assertRaisesRegex(RuntimeError, "API_HASH"):
            validate_api_credentials(1, "")

    def test_build_session_output_contains_secret_warning(self) -> None:
        output = build_session_output("abc123")

        self.assertIn("TELEGRAM_SESSION", output)
        self.assertIn("abc123", output)
        self.assertIn("不要提交", output)

    async def test_resolve_notify_target_uses_me_for_current_user_id(self) -> None:
        client = Mock()
        me = Mock()
        me.id = 5795587098
        client.get_me = AsyncMock(return_value=me)

        target = await resolve_notify_target(client, "5795587098")

        self.assertEqual(target, "me")

    async def test_resolve_notify_target_accepts_me_alias(self) -> None:
        client = Mock()

        target = await resolve_notify_target(client, "self")

        self.assertEqual(target, "me")

    async def test_send_summary_notification_ignores_resolution_failure(self) -> None:
        client = Mock()
        client.get_me = AsyncMock(side_effect=ValueError("not found"))
        client.send_message = AsyncMock()
        result = parse_bot_reply("你已经签到过了，明天再来吧", command="赌狗签到")

        sent = await send_summary_notification(client, "5795587098", result)

        self.assertFalse(sent)
        client.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
