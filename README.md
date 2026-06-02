# HDHive Telegram 自动签到

使用 GitHub Actions + Telethon，定时向已绑定 HDHive 账号的 Telegram 机器人发送签到命令。

这个版本不再驱动 HDHive 网页，也不再依赖 Playwright。签到走 Telegram 机器人入口，因此不会触发网页端 Cloudflare 验证。

## 工作方式

1. GitHub Actions 按计划启动。
2. Telethon 使用你的 Telegram 用户会话登录。
3. 向 HDHive 机器人发送 `赌狗签到`，或你配置的其他命令。
4. 等待机器人回复并解析结果。
5. 将结果写入 `artifacts/latest-results.json` 和 GitHub Actions Summary。
6. 如配置 `TELEGRAM_NOTIFY_CHAT_ID`，会额外发送一条汇总通知。

## GitHub Actions 配置

在仓库的 **Settings -> Secrets and variables -> Actions** 中配置。

### Secrets

- `TELEGRAM_API_ID`：Telegram API ID。
- `TELEGRAM_API_HASH`：Telegram API Hash。
- `TELEGRAM_SESSION`：Telethon StringSession。
- `HDHIVE_BOT_USERNAME`：HDHive 机器人用户名，例如 `@example_bot`。

### Variables

- `HDHIVE_SIGN_COMMAND`：签到命令，默认 `赌狗签到`。
- `TELEGRAM_RESPONSE_TIMEOUT_SECONDS`：等待机器人回复的秒数，默认 `60`。
- `TELEGRAM_NOTIFY_CHAT_ID`：可选，发送结果通知的 Telegram chat id。

默认定时任务为北京时间每天 `06:23`：

```yaml
cron: "23 22 * * *"
```

## 生成 TELEGRAM_SESSION

先在本地安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

设置 API 信息并生成会话：

```bash
export TELEGRAM_API_ID="123456"
export TELEGRAM_API_HASH="your-api-hash"
python scripts/generate_telegram_session.py
```

脚本会要求输入 Telegram 手机号、验证码，以及可能存在的二步验证密码。最后输出的 `TELEGRAM_SESSION` 只保存到 GitHub Secrets，不要提交到仓库。

## 本地运行

复制配置模板：

```bash
cp local.config.example.json local.config.json
```

填好 `local.config.json` 后运行：

```bash
python scripts/telegram_checkin.py
```

本地配置优先级高于环境变量，方便调试。

## 结果判断

脚本会解析机器人回复：

- 包含 `签到成功`：状态为 `success`，并尝试提取积分。
- 包含 `已经签到` 或 `明天再来`：状态也为 `success`，标记 `already_signed=true`。
- 包含 `失败`：状态为 `failed`。
- 其他回复或超时：状态为 `unknown`。

## 安全说明

`TELEGRAM_SESSION` 等同于 Telegram 用户登录凭证。建议使用专门绑定 HDHive 机器人的 Telegram 账号，不要在日志、截图、README 或 Issue 中公开它。

## Contact

如果你在使用过程中遇到问题，欢迎联系我：

- Telegram: [@suversal](https://t.me/suversal)
- Email: `suyloveslife@gmail.com`
