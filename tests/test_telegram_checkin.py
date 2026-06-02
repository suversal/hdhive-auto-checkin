import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.telegram_checkin import (
    build_markdown_summary,
    build_summary_message,
    parse_bot_reply,
    write_outputs,
)


class TelegramReplyParsingTest(unittest.TestCase):
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

        self.assertIn("- Status: `success`", summary)
        self.assertIn("- Points: `16`", summary)

    def test_write_outputs_saves_latest_results_json(self) -> None:
        result = parse_bot_reply("🎰 签到成功，获得 16 积分", command="赌狗签到")

        with TemporaryDirectory() as temp_dir:
            write_outputs(result, Path(temp_dir))
            saved = Path(temp_dir, "latest-results.json").read_text(encoding="utf-8")

        self.assertIn('"status": "success"', saved)
        self.assertIn('"points": 16', saved)


if __name__ == "__main__":
    unittest.main()
