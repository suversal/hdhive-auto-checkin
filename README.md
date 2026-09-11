<div align="center">
  <h1>🧩 Telegram 自动任务 🧩</h1>
  <p><b>基于 Python + Telethon + GitHub Actions 的 Telegram 定时消息工具</b></p>
  <p><b>支持多个 Telegram 账号，每个账号配置多个任务，定时给不同机器人发送不同消息，并汇总展示机器人原始返回。</b></p>
  <br/>
</div>

---

## 核心特性

- 多 Telegram 账号：每个账号使用自己的 Telethon `StringSession`。
- 多任务配置：一个 Telegram 账号下面可以配置多个机器人任务。
- 原始返回展示：不强行判断成功或失败，只展示机器人返回内容。
- 账号内通知：每个 Telegram 账号可以把自己的任务结果发到 Saved Messages 或指定 chat。
- 总汇总通知：可以用 Telegram Bot API 把所有账号、所有任务汇总发到主账号。
- GitHub Actions：支持定时触发、手动触发、push 触发。
- 本地代理：支持 Clash/Mihomo 这类本机代理，解决 Telethon 连接 Telegram 超时问题。

## 工作方式

1. GitHub Actions 或本地命令启动脚本。
2. 脚本读取 Telegram API、账号、任务配置。
3. 每个 Telegram 账号建立一次 Telethon 连接。
4. 同一个账号下的多个任务按顺序执行。
5. 每个任务向指定机器人发送指定消息。
6. 脚本等待机器人回复。
7. 把机器人返回写入 `artifacts/latest-results.json`。
8. 如果配置了通知，就发送账号通知和总汇总通知。

## 获取 Telegram api_id 和 api_hash

1. 打开 [my.telegram.org/apps](https://my.telegram.org/apps)。
2. 使用你的 Telegram 手机号登录。
3. 创建 application。
4. 表单可以按个人用途填写，例如：

```text
App title: Telegram Auto Tasks
Short name: telegram_auto_tasks
URL: https://github.com/suversal
Platform: Desktop
Description: Personal Telegram automation
```

创建成功后会得到：

```text
api_id
api_hash
```

`api_hash` 不要公开。

## 生成 Telegram Session

每个 Telegram 账号都需要单独生成一个 session。

先安装依赖：

```bash
cd /Users/sue/hdhive-auto-checkin
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

打开 [scripts/generate_telegram_session.py](/Users/sue/hdhive-auto-checkin/scripts/generate_telegram_session.py)，把顶部变量改成你的真实值：

```python
API_ID = 123456
API_HASH = "your-api-hash"
```

运行：

```bash
python scripts/generate_telegram_session.py
```

按提示输入：

```text
Telegram 手机号（带国家区号，例如 +8613800000000）:
Telegram 验证码:
Telegram 二步验证密码:
```

成功后会输出一长串 `TELEGRAM_SESSION`，把它填到对应 Telegram 账号的 `session` 字段。

## 本地配置

复制模板：

```bash
cp local.config.example.json local.config.json
```

本地配置必须是标准 JSON，不能写 `// 注释`，否则 IDEA 和脚本都会报错。字段说明看下方“字段说明”。配置结构是“Telegram 账号 -> 多个任务”：

```json
{
  "project_name": "Telegram 自动任务",
  "telegram_api_id": "123456",
  "telegram_api_hash": "your-api-hash",
  "telegram_bot_token": "your-telegram-bot-token",
  "telegram_summary_notify_chat_id": "123456789",
  "telegram_response_timeout_seconds": "60",
  "telegram_proxy": {
    "type": "socks5",
    "host": "127.0.0.1",
    "port": 7897
  },
  "telegram_accounts": [
    {
      "name": "账号 A",
      "session": "first-account-telethon-string-session",
      "notify_chat_id": "me",
      "tasks": [
        {
          "name": "HDHive 自动签到",
          "type": "签到",
          "target_account": "suloveslife@qq.com",
          "bot_username": "@HDHiveBot",
          "message": "赌狗签到"
        },
        {
          "name": "癫影自动签到",
          "type": "签到",
          "target_account": "xxxxx",
          "bot_username": "@dianyingbalala_bot",
          "message": "/lqd"
        }
      ]
    }
  ]
}
```

字段说明：

- `project_name`：通知标题里显示的项目名。
- `telegram_api_id`：my.telegram.org 申请到的 `api_id`。
- `telegram_api_hash`：my.telegram.org 申请到的 `api_hash`。
- `telegram_bot_token`：可选。用于发送所有任务的总汇总通知。
- `telegram_summary_notify_chat_id`：可选。接收总汇总通知的 chat id。
- `telegram_response_timeout_seconds`：每个任务等待机器人回复的最长秒数。
- `telegram_proxy`：可选。Telegram 连接代理，本地 Clash/Mihomo 常用 `socks5://127.0.0.1:7897`。
- `telegram_accounts`：Telegram 登录账号数组。
- `telegram_accounts[].name`：Telegram 登录账号名称，只用于日志和通知展示。
- `telegram_accounts[].session`：这个 Telegram 账号生成的 session。
- `telegram_accounts[].notify_chat_id`：可选。这个 Telegram 账号执行完自己的任务后，把结果发到哪里。
- `telegram_accounts[].tasks`：这个 Telegram 账号要执行的任务数组。
- `tasks[].name`：任务名称，例如 `HDHive 自动签到`。
- `tasks[].type`：任务类型，例如 `签到`、`提醒`、`查询`。
- `tasks[].target_account`：业务账号名称，只用于展示，例如站点账号邮箱。
- `tasks[].bot_username`：要发送消息的 Telegram 机器人 username。
- `tasks[].message`：要发送给机器人的消息内容。

## 通知配置

账号自己的通知：

```json
"notify_chat_id": "me"
```

含义：这个 Telegram 账号的任务执行完后，把该账号下所有任务结果发到自己的 Saved Messages。

所有任务的汇总通知：

```json
"telegram_bot_token": "your-telegram-bot-token",
"telegram_summary_notify_chat_id": "123456789"
```

含义：所有账号、所有任务执行完后，由 `telegram_bot_token` 对应的机器人发送一条总汇总。

`notify_chat_id` 支持：

- `""`：不发送账号通知。
- `"me"`：发送到当前 session 对应账号的 Saved Messages。
- `"@username"`：发送给指定 Telegram 用户。
- 数字 chat id：发送到指定用户、群组或频道。

`telegram_summary_notify_chat_id` 由 Bot API 使用，不支持 `"me"`；建议填写数字 chat id。接收方需要先和这个通知机器人发起过会话。

## Telegram 代理

如果本地运行时出现：

```text
Attempt 1 at connecting failed: TimeoutError
Connection to Telegram failed 5 time(s)
```

说明 Python/Telethon 没有连上 Telegram。即使 Telegram 桌面客户端能用，命令行脚本也不一定自动使用系统代理。

本地 Clash/Mihomo 可以在配置里写：

```json
"telegram_proxy": {
  "type": "socks5",
  "host": "127.0.0.1",
  "port": 7897
}
```

也可以临时通过环境变量测试：

```bash
TELEGRAM_PROXY_URL=socks5://127.0.0.1:7897 python scripts/telegram_checkin.py
```

注意：`127.0.0.1:7897` 只表示当前运行脚本的机器。GitHub Actions 里这个地址不是你的 Mac，不要直接把本机 Clash 地址填到 Actions。

## 本地测试

确认当前分支：

```bash
git branch --show-current
```

安装依赖：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

单元测试：

```bash
TELEGRAM_LOCAL_CONFIG_PATH=/private/tmp/telegram-auto-tasks-missing-local-config.json python -m unittest discover -s tests
```

运行真实任务：

```bash
python scripts/telegram_checkin.py
```

如果需要本地代理：

```bash
TELEGRAM_PROXY_URL=socks5://127.0.0.1:7897 python scripts/telegram_checkin.py
```

结果文件：

```text
artifacts/latest-results.json
```

## GitHub Actions 配置

进入仓库：

```text
Settings -> Secrets and variables -> Actions
```

### Secrets

必填：

```text
TELEGRAM_API_ID
TELEGRAM_API_HASH
TELEGRAM_ACCOUNTS_JSON
```

`TELEGRAM_ACCOUNTS_JSON` 只填账号数组，不要包含外层对象，也不要包含 `telegram_api_id`、`telegram_api_hash`、`telegram_bot_token`。

注意：GitHub Secrets / Variables 里也必须是严格 JSON，不能带注释。

如果需要总汇总通知，再添加：

```text
TELEGRAM_BOT_TOKEN
```

示例：

```json
[
  {
    "name": "账号 A",
    "session": "first-account-telethon-string-session",
    "notify_chat_id": "me",
    "tasks": [
      {
        "name": "HDHive 自动签到",
        "type": "签到",
        "target_account": "suloveslife@qq.com",
        "bot_username": "@HDHiveBot",
        "message": "赌狗签到"
      },
      {
        "name": "癫影自动签到",
        "type": "签到",
        "target_account": "xxxxx",
        "bot_username": "@dianyingbalala_bot",
        "message": "/lqd"
      }
    ]
  }
]
```

### Variables

可选添加：

```text
TELEGRAM_PROJECT_NAME = Telegram 自动任务
TELEGRAM_RESPONSE_TIMEOUT_SECONDS = 60
TELEGRAM_SUMMARY_NOTIFY_CHAT_ID = 123456789
```

如果你配置了 `TELEGRAM_SUMMARY_NOTIFY_CHAT_ID`，就必须同时配置 `TELEGRAM_BOT_TOKEN`，否则脚本会正常执行任务，但不会发送总汇总通知。

## 触发方式

工作流支持：

- 定时触发：北京时间每天 `05:23`。
- 手动触发：GitHub Actions 页面点击 `Run workflow`。
- push 触发：当 `scripts/**`、`tests/**`、workflow、依赖或配置模板变化时触发。

定时配置在 [.github/workflows/checkin.yml](/Users/sue/hdhive-auto-checkin/.github/workflows/checkin.yml)：

```yaml
cron: "23 21 * * *"
```

这是 UTC 时间，对应北京时间每天 `05:23`。

## 汇总通知格式

```text
🧩 Telegram 自动任务汇总
━━━━━━━━━━━━━━━━━━
🕒 执行时间：2026-09-11 21:54:19
📦 任务数量：3

👥 Telegram账号：账号 A

⎡ 🏷️ 任务名称：HDHive 自动签到
├ 📌 任务类型：签到
├ 👤 任务账号：suloveslife@qq.com
├ 🤖 目标机器人：@HDHiveBot
├ 📤 发送内容：赌狗签到
⎣ 📝 机器人返回：你已经签到过了，明天再来吧

⎡ 🏷️ 任务名称：癫影自动签到
├ 📌 任务类型：签到
├ 👤 任务账号：xxxxx
├ 🤖 目标机器人：@dianyingbalala_bot
├ 📤 发送内容：/lqd
⎣ 📝 机器人返回：超过 60 秒未收到机器人回复
```

## 旧配置兼容

脚本仍兼容旧的 `hdhive_telegram_accounts_json` / `HDHIVE_TELEGRAM_ACCOUNTS_JSON`，但推荐迁移到新的 `telegram_accounts` / `TELEGRAM_ACCOUNTS_JSON`。

旧格式每条配置只能表示一个任务；新格式是一个 Telegram 账号下面挂多个任务，更适合长期维护。

## 常见问题

### `ModuleNotFoundError: No module named 'telethon'`

没有安装依赖，或当前终端没有激活项目虚拟环境。

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### `PasswordHashInvalidError`

Telegram 二步验证密码错误。这里输入的是 Telegram Two-Step Verification Password，不是短信验证码。

### `Cannot find any entity corresponding to "5795587098"`

通知目标无法解析。发给当前账号自己时，建议填：

```json
"notify_chat_id": "me"
```

### 本地直接执行还是超时

确认配置里有代理，或者执行时带上：

```bash
TELEGRAM_PROXY_URL=socks5://127.0.0.1:7897 python scripts/telegram_checkin.py
```

### GitHub Actions 里没有收到通知

检查：

- `TELEGRAM_BOT_TOKEN` 是否配置。
- `TELEGRAM_SUMMARY_NOTIFY_CHAT_ID` 是否配置。
- 接收方是否主动和通知机器人发过消息。
- `TELEGRAM_ACCOUNTS_JSON` 是否是纯账号数组。

## 安全说明

`TELEGRAM_SESSION` 等同于 Telegram 登录凭证。任何拿到它的人，都可能用你的 Telegram 账号发消息。

请注意：

- 不要把真实 session 提交到仓库。
- 不要把真实 session 发到 Issue、日志、截图里。
- 建议使用专门跑自动任务的 Telegram 账号。
- 如果怀疑 session 泄露，去 Telegram App 里终止对应登录会话，然后重新生成。

## 联系方式

如果你在使用过程中遇到问题，欢迎联系我：

- Telegram: [https://t.me/suversal](https://t.me/suversal)
- Email: suyloveslife@gmail.com
