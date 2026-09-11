import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs
from unittest.mock import AsyncMock, Mock

from scripts.generate_telegram_session import build_session_output, validate_api_credentials
from scripts.telegram_checkin import (
    TelegramTaskResult,
    build_account_notification_message,
    build_markdown_summary,
    build_summary_message,
    build_summary_notification_message,
    load_account_configs_from_mapping,
    load_runtime_config_from_mapping,
    load_summary_notify_chat_id_from_mapping,
    load_telegram_bot_token_from_mapping,
    parse_telegram_proxy,
    resolve_notify_target,
    send_account_notification,
    send_run_summary_notification,
    send_summary_notification,
    write_outputs,
)


class TelegramTaskConfigTest(unittest.IsolatedAsyncioTestCase):
    def test_load_runtime_config_accepts_account_grouped_tasks(self) -> None:
        runtime = load_runtime_config_from_mapping(
            {
                "project_name": "Telegram 自动任务",
                "telegram_api_id": "123",
                "telegram_api_hash": "hash",
                "telegram_response_timeout_seconds": "30",
                "telegram_accounts": [
                    {
                        "name": "账号 A",
                        "session": "session-a",
                        "notify_chat_id": "me",
                        "tasks": [
                            {
                                "name": "HDHive 自动签到",
                                "type": "签到",
                                "target_account": "suloveslife@qq.com",
                                "bot_username": "@HDHiveBot",
                                "message": "赌狗签到",
                            },
                            {
                                "name": "癫影自动签到",
                                "type": "签到",
                                "target_account": "xxxxx",
                                "bot_username": "@dianyingbalala_bot",
                                "message": "/lqd",
                            },
                        ],
                    }
                ],
            }
        )

        self.assertEqual(runtime.project_name, "Telegram 自动任务")
        self.assertEqual(len(runtime.accounts), 1)
        self.assertEqual(runtime.accounts[0].name, "账号 A")
        self.assertEqual(runtime.accounts[0].notify_chat_id, "me")
        self.assertEqual(len(runtime.accounts[0].tasks), 2)
        self.assertEqual(runtime.accounts[0].tasks[0].message, "赌狗签到")
        self.assertEqual(runtime.accounts[0].tasks[1].bot_username, "@dianyingbalala_bot")

    def test_load_account_configs_keeps_legacy_compatibility(self) -> None:
        configs = load_account_configs_from_mapping(
            {
                "telegram_api_id": "123",
                "telegram_api_hash": "hash",
                "hdhive_telegram_accounts_json": [
                    {"name": "account-a", "session": "session-a", "bot_username": "@bot_a"},
                    {"name": "account-b", "session": "session-b", "bot_username": "@bot_b", "command": "签到"},
                ],
            }
        )

        self.assertEqual(len(configs), 2)
        self.assertEqual(configs[0].name, "account-a")
        self.assertEqual(configs[0].command, "赌狗签到")
        self.assertEqual(configs[1].name, "account-b")
        self.assertEqual(configs[1].command, "签到")

    def test_load_runtime_config_requires_tasks(self) -> None:
        with self.assertRaisesRegex(Exception, "tasks"):
            load_runtime_config_from_mapping(
                {
                    "telegram_api_id": "123",
                    "telegram_api_hash": "hash",
                    "telegram_accounts": [
                        {"name": "账号 A", "session": "session-a", "tasks": []}
                    ],
                }
            )

    def test_load_runtime_config_accepts_proxy_object(self) -> None:
        fake_socks = Mock(SOCKS5=10, SOCKS4=20, HTTP=30)
        with unittest.mock.patch("scripts.telegram_checkin.socks", fake_socks):
            runtime = load_runtime_config_from_mapping(
                {
                    "telegram_api_id": "123",
                    "telegram_api_hash": "hash",
                    "telegram_proxy": {
                        "type": "socks5",
                        "host": "127.0.0.1",
                        "port": 7897,
                    },
                    "telegram_accounts": [
                        {
                            "name": "账号 A",
                            "session": "session-a",
                            "tasks": [{"name": "任务 A", "bot_username": "@bot_a", "message": "签到"}],
                        }
                    ],
                }
            )

        self.assertEqual(runtime.proxy, (10, "127.0.0.1", 7897, True))
        self.assertEqual(runtime.proxy_label, "socks5://127.0.0.1:7897")

    def test_parse_telegram_proxy_accepts_url(self) -> None:
        fake_socks = Mock(SOCKS5=10, SOCKS4=20, HTTP=30)
        with unittest.mock.patch("scripts.telegram_checkin.socks", fake_socks):
            proxy, label = parse_telegram_proxy("socks5://127.0.0.1:7897")

        self.assertEqual(proxy, (10, "127.0.0.1", 7897, True))
        self.assertEqual(label, "socks5://127.0.0.1:7897")

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

    def test_summary_message_contains_raw_bot_reply_without_success_stats(self) -> None:
        result = TelegramTaskResult(
            telegram_account_name="账号 A",
            task_name="HDHive 自动签到",
            task_type="签到",
            target_account="suloveslife@qq.com",
            bot_username="@HDHiveBot",
            sent_message="赌狗签到",
            status="replied",
            reply_text="你已经签到过了，明天再来吧",
            elapsed_seconds=1.2,
        )

        message = build_summary_message(result)

        self.assertIn("Telegram 自动任务", message)
        self.assertIn("任务名称：HDHive 自动签到", message)
        self.assertIn("机器人返回：你已经签到过了，明天再来吧", message)
        self.assertNotIn("统计汇总", message)
        self.assertNotIn("签到成功", message)

    def test_build_summary_notification_message_groups_by_telegram_account(self) -> None:
        results = [
            TelegramTaskResult(
                telegram_account_name="账号 A",
                task_name="HDHive 自动签到",
                task_type="签到",
                target_account="suloveslife@qq.com",
                bot_username="@HDHiveBot",
                sent_message="赌狗签到",
                status="replied",
                reply_text="你已经签到过了，明天再来吧",
            ),
            TelegramTaskResult(
                telegram_account_name="账号 A",
                task_name="癫影自动签到",
                task_type="签到",
                target_account="xxxxx",
                bot_username="@dianyingbalala_bot",
                sent_message="/lqd",
                status="timeout",
                reply_text="超过 60 秒未收到机器人回复",
            ),
            TelegramTaskResult(
                telegram_account_name="账号 B",
                task_name="任务 B",
                task_type="提醒",
                target_account="xx",
                bot_username="@other_bot",
                sent_message="hello",
                status="replied",
                reply_text="ok",
            ),
        ]

        message = build_summary_notification_message("Telegram 自动任务", results)

        self.assertIn("🧩 <b>Telegram 自动任务汇总</b>", message)
        self.assertIn("📦 任务数量：3", message)
        self.assertIn("👥 Telegram账号：<code>账号 A</code>", message)
        self.assertIn("⎡ 🏷️ 任务名称：癫影自动签到", message)
        self.assertIn("├ 📤 发送内容：<code>/lqd</code>", message)
        self.assertIn("⎣ 📝 机器人返回：超过 60 秒未收到机器人回复", message)
        self.assertIn("👥 Telegram账号：<code>账号 B</code>", message)
        self.assertNotIn("成功", message)
        self.assertNotIn("失败", message)

    def test_build_account_notification_message_lists_one_account_tasks(self) -> None:
        result = TelegramTaskResult(
            telegram_account_name="账号 A",
            task_name="任务 A",
            task_type="签到",
            target_account="a@example.com",
            bot_username="@bot",
            sent_message="签到",
            status="replied",
            reply_text="ok",
        )

        message = build_account_notification_message("Telegram 自动任务", [result])

        self.assertIn("👥 Telegram账号：<code>账号 A</code>", message)
        self.assertIn("任务名称：任务 A", message)
        self.assertIn("机器人返回：ok", message)

    def test_markdown_summary_contains_raw_bot_reply(self) -> None:
        result = TelegramTaskResult(
            telegram_account_name="账号 A",
            task_name="任务 A",
            task_type="签到",
            target_account="a@example.com",
            bot_username="@bot",
            sent_message="签到",
            status="replied",
            reply_text="ok",
        )

        summary = build_markdown_summary(result)

        self.assertIn("# Telegram Automated Tasks", summary)
        self.assertIn("| 账号 A | 任务 A | 签到 | a@example.com | `@bot` | `签到` | `replied` | ok |", summary)

    def test_write_outputs_saves_latest_results_json(self) -> None:
        result = TelegramTaskResult(
            telegram_account_name="账号 A",
            task_name="任务 A",
            task_type="签到",
            target_account="a@example.com",
            bot_username="@bot",
            sent_message="签到",
            status="replied",
            reply_text="ok",
        )

        with TemporaryDirectory() as temp_dir:
            write_outputs(result, Path(temp_dir))
            saved = Path(temp_dir, "latest-results.json").read_text(encoding="utf-8")

        self.assertIn('"total": 1', saved)
        self.assertIn('"reply_text": "ok"', saved)

    def test_send_run_summary_notification_uses_telegram_bot_api(self) -> None:
        result = TelegramTaskResult(
            telegram_account_name="账号 A",
            task_name="任务 A",
            task_type="签到",
            target_account="a@example.com",
            bot_username="@bot",
            sent_message="签到",
            status="replied",
            reply_text="ok",
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
            sent = send_run_summary_notification("bot-token", "123456", "Telegram 自动任务", [result])

        self.assertTrue(sent)
        self.assertEqual(captured["url"], "https://api.telegram.org/botbot-token/sendMessage")
        self.assertEqual(captured["timeout"], 30)
        payload = parse_qs(captured["body"])
        self.assertEqual(payload["chat_id"], ["123456"])
        self.assertEqual(payload["parse_mode"], ["HTML"])
        self.assertIn("任务 A", payload["text"][0])

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
        result = TelegramTaskResult(
            telegram_account_name="账号 A",
            task_name="任务 A",
            task_type="签到",
            target_account="a@example.com",
            bot_username="@bot",
            sent_message="签到",
            status="replied",
            reply_text="ok",
        )

        sent = await send_summary_notification(client, "5795587098", result)

        self.assertFalse(sent)
        client.send_message.assert_not_called()

    async def test_send_account_notification_uses_grouped_message(self) -> None:
        client = Mock()
        client.send_message = AsyncMock()
        result = TelegramTaskResult(
            telegram_account_name="账号 A",
            task_name="任务 A",
            task_type="签到",
            target_account="a@example.com",
            bot_username="@bot",
            sent_message="签到",
            status="replied",
            reply_text="ok",
        )

        sent = await send_account_notification(client, "me", "Telegram 自动任务", [result])

        self.assertTrue(sent)
        client.send_message.assert_awaited_once()

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


if __name__ == "__main__":
    unittest.main()
