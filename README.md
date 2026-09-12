<div align="center">
  <h1>🧩 Telegram 自动任务 🧩</h1>
  <p><b>基于 Python + Telethon + GitHub Actions 的 Telegram 定时消息工具</b></p>
  <p><b>支持多个 Telegram 账号，每个账号配置多个任务，定时给不同机器人发送不同消息，并汇总展示机器人原始返回。</b></p>
  <br/>
</div>

---

> 本项目最初是为 HDHive 自动签到编写的，后来升级为通用的 Telegram 自动发消息方案。如果你是为了查看旧版 HDHive 绑定机器人签到说明，可以参考备份文档：[README.hdhive.md](/Users/sue/hdhive-auto-checkin/README.hdhive.md)。

## 项目介绍

这个项目现在定位为一个通用的 Telegram 自动任务工具。它保留了最初 HDHive 自动签到场景里沉淀下来的多账号、定时执行、结果通知能力，但不再把逻辑写死在 HDHive 上。

它不再只绑定某一个站点或某一种签到逻辑，而是做一件更通用的事情：

1. 使用你的 Telegram 账号登录。
2. 按配置给不同的 Telegram 机器人发送消息。
3. 等待机器人回复。
4. 把机器人返回原样记录下来。
5. 可选发送账号通知和总汇总通知。

适合这类场景：

- 每天给某个机器人发送签到消息。
- 用多个 Telegram 账号分别执行不同任务。
- 同一个 Telegram 账号给多个机器人发送不同指令。
- 定时执行命令，并把机器人返回集中推送给主账号。

## 核心特性

- 多 Telegram 账号：每个账号使用自己的 Telethon `StringSession`。
- 多任务配置：一个 Telegram 账号下面可以配置多个任务。
- 通用机器人消息：每个任务都能指定目标机器人和发送内容。
- 原始返回展示：不强行判断成功或失败，只展示机器人返回内容。
- 账号内通知：每个 Telegram 账号可以把自己的任务结果发到 Saved Messages 或指定 chat。
- 总汇总通知：可以通过 Telegram Bot API 把所有账号、所有任务的结果发到主账号。
- GitHub Actions：支持定时触发、手动触发、push 触发。
- 本地代理：支持 Clash/Mihomo 这类本机代理，解决 Telethon 连接 Telegram 超时问题。

## 工作流程

1. GitHub Actions 到点运行，或者你在本地手动运行脚本。
2. 脚本读取 Telegram API 信息、账号配置、任务配置。
3. 每个 Telegram 账号建立一次 Telethon 连接。
4. 同一个账号下的多个任务按顺序执行。
5. 每个任务向指定机器人发送指定消息。
6. 脚本等待机器人回复。
7. 结果写入 `artifacts/latest-results.json`。
8. 如果配置了通知，发送账号自己的通知和所有任务的汇总通知。

## 准备工作

你需要准备：

- 一个 GitHub 仓库，用来运行 GitHub Actions。
- 一个或多个 Telegram 账号。
- Telegram API 的 `api_id` 和 `api_hash`。
- 每个 Telegram 账号对应的 `StringSession`。
- 你要发送消息的目标机器人 username，例如 `@HDHiveBot`。
- 可选：一个 Telegram Bot Token，用来发送总汇总通知。

## 获取 Telegram api_id 和 api_hash

1. 打开 [my.telegram.org/apps](https://my.telegram.org/apps)。
2. 使用你的 Telegram 手机号登录。
3. 点击创建 application。
4. 根据自己的需求填写表单：

```text
App title: Telegram Auto Tasks
Short name: telegram_auto_tasks
URL: https://github.com/suversal
Platform: Desktop
Description: Personal Telegram automation
```
<img width="617" height="635" alt="image" src="https://github.com/user-attachments/assets/11cb07ec-3d66-4a62-9467-8a96b7bfa338" />

5. 创建成功后，页面会显示：

```text
api_id
api_hash
```

这两个值后面会用到。不要公开 `api_hash`。
<img width="745" height="579" alt="image" src="https://github.com/user-attachments/assets/80e10bf9-02ae-4179-a968-8e602928879a" />

## 生成 TELEGRAM_SESSION

`TELEGRAM_SESSION` 是 Telegram 登录会话。每个 Telegram 账号都要单独生成一个。

先安装依赖：

```bash
cd /Users/sue/hdhive-auto-checkin
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

打开 [scripts/generate_telegram_session.py](/Users/sue/hdhive-auto-checkin/scripts/generate_telegram_session.py)，把顶部的变量改成你的真实值：

```python
API_ID = 123456
API_HASH = "your-api-hash"
```

运行脚本：

```bash
python scripts/generate_telegram_session.py
```

脚本会依次让你输入：

```text
Telegram 手机号（带国家区号，例如 +8613800000000）:
Telegram 验证码:
Telegram 二步验证密码:
```

如果你的账号没有开启二步验证，就不会要求输入二步验证密码。

成功后会输出：

```text
TELEGRAM_SESSION:
一长串字符串
```

把这一整串保存下来。它就是该 Telegram 账号的 session。
如果你有两个 Telegram 账号，就对第二个账号再运行一次这个脚本，生成第二个 session。

<img width="835" height="433" alt="image" src="https://github.com/user-attachments/assets/736f610b-b4f5-490c-b587-2b4c7f8225f1" />

## 本地配置

复制模板：

```bash
cp local.config.example.json local.config.json
```

本地配置必须是标准 JSON，不能写 `// 注释`。

配置结构是：

```text
Telegram 账号 -> 多个任务
```

示例：

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

## 配置字段说明

顶层字段：

- `project_name`：通知标题里显示的项目名。
- `telegram_api_id`：你在 my.telegram.org 申请到的 `api_id`。
- `telegram_api_hash`：你在 my.telegram.org 申请到的 `api_hash`。
- `telegram_bot_token`：可选。用于发送所有任务的总汇总通知。
- `telegram_summary_notify_chat_id`：可选。接收总汇总通知的 chat id。
- `telegram_response_timeout_seconds`：每个任务等待机器人回复的最长时间，默认建议 `60` 秒。
- `telegram_proxy`：可选。本地连接 Telegram 超时时使用。
- `telegram_accounts`：Telegram 登录账号数组。

`telegram_accounts` 中每个账号的字段：

- `name`：Telegram 登录账号名称，只用于日志和通知展示。
- `session`：这个 Telegram 账号生成的 `StringSession`。
- `notify_chat_id`：可选。这个账号自己的任务结果通知目标。
- `tasks`：这个 Telegram 账号要执行的任务数组。

`tasks` 中每个任务的字段：

- `name`：任务名称，例如 `HDHive 自动签到`。
- `type`：任务类型，例如 `签到`、`提醒`、`查询`。
- `target_account`：业务账号名称，只用于展示，例如站点账号邮箱。
- `bot_username`：要发送消息的 Telegram 机器人 username。
- `message`：要发送给机器人的消息内容。

## 通知配置

通知分两种。

### 账号自己的通知

配置在每个 Telegram 账号里：

```json
"notify_chat_id": "me"
```

含义：这个 Telegram 账号执行完自己的任务后，把该账号下所有任务结果发到自己的 Saved Messages。

`notify_chat_id` 支持：

- `""`：不发送账号通知。
- `"me"`：发送到当前 session 对应账号的 Saved Messages。
- `"@username"`：发送给指定 Telegram 用户。
- 数字 chat id：发送到指定用户、群组或频道。

### 所有任务汇总通知

配置在顶层：

```json
"telegram_bot_token": "your-telegram-bot-token",
"telegram_summary_notify_chat_id": "123456789"
```

含义：所有账号、所有任务执行完后，由 `telegram_bot_token` 对应的机器人发送一条总汇总。

注意：

- `telegram_summary_notify_chat_id` 不支持 `"me"`。
- 接收方需要先和这个通知机器人发起过会话。
- 如果配置了 `telegram_summary_notify_chat_id`，就必须同时配置 `telegram_bot_token`。

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

先跑单元测试：

```bash
TELEGRAM_LOCAL_CONFIG_PATH=/private/tmp/telegram-auto-tasks-missing-local-config.json python -m unittest discover -s tests
```

再跑真实任务：

```bash
python scripts/telegram_checkin.py
```

如果本地需要代理：

```bash
TELEGRAM_PROXY_URL=socks5://127.0.0.1:7897 python scripts/telegram_checkin.py
```

结果会写到：

```text
artifacts/latest-results.json
```

## GitHub Actions 配置

进入你的 GitHub 仓库：

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

如果需要所有任务汇总通知，再添加：

```text
TELEGRAM_BOT_TOKEN
```

`TELEGRAM_ACCOUNTS_JSON` 只填 `telegram_accounts` 这个数组，不要包含外层对象。

例如：

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

GitHub Secrets 里必须是严格 JSON，不能写注释。

### Variables

可选添加：

```text
TELEGRAM_PROJECT_NAME = Telegram 自动任务
TELEGRAM_RESPONSE_TIMEOUT_SECONDS = 60
TELEGRAM_SUMMARY_NOTIFY_CHAT_ID = 123456789
```

如果你配置了 `TELEGRAM_SUMMARY_NOTIFY_CHAT_ID`，就必须同时配置 `TELEGRAM_BOT_TOKEN`。

## 触发方式

工作流支持三种触发方式：

- 定时触发：北京时间每天 `05:23`。
- 手动触发：GitHub Actions 页面点击 `Run workflow`。
- push 触发：当 `scripts/**`、`tests/**`、workflow、依赖或配置模板变化时触发。

定时配置在 [.github/workflows/checkin.yml](/Users/sue/hdhive-auto-checkin/.github/workflows/checkin.yml)：

```yaml
cron: "23 21 * * *"
```

这个时间是 UTC，对应北京时间每天 `05:23`。

## 汇总通知格式

汇总通知大致如下：

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

旧版 HDHive 专用说明已经备份到：[README.hdhive.md](/Users/sue/hdhive-auto-checkin/README.hdhive.md)。

## 常见问题

### `ModuleNotFoundError: No module named 'telethon'`

没有安装依赖，或当前终端没有激活项目虚拟环境。

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### `PasswordHashInvalidError`

Telegram 二步验证密码错误。

这里要输入的是 Telegram 的 Two-Step Verification Password，不是短信验证码。

### `PhoneCodeInvalidError`

验证码错误。重新运行 `generate_telegram_session.py`，输入最新验证码。

### `PhoneCodeExpiredError`

验证码过期。重新运行脚本获取新验证码。

### `Cannot find any entity corresponding to "5795587098"`

通知目标无法解析。发给当前账号自己时，建议填：

```json
"notify_chat_id": "me"
```

### `local.config.json JSON 格式错误`

本地配置不是合法 JSON。常见原因：

- 少了逗号。
- 字符串没有用双引号。
- JSON 里写了 `// 注释`。
- JSON 结尾后面还有多余内容。

可以用下面命令检查：

```bash
python -m json.tool local.config.json
```

### GitHub Actions 里没有收到通知

先看 Actions 日志：

- 是否成功读取了账号配置。
- 是否目标机器人有回复。
- 是否通知发送失败。
- 是否配置了 `TELEGRAM_BOT_TOKEN`。
- `TELEGRAM_SUMMARY_NOTIFY_CHAT_ID` 是否是机器人可发送的 chat id。

## 安全说明

`TELEGRAM_SESSION` 等同于 Telegram 登录凭证。任何拿到它的人，都可能用你的 Telegram 账号发消息。

请注意：

- 不要把真实 session 提交到仓库。
- 不要把真实 session 发到 Issue、日志、截图里。
- 建议使用专门跑自动任务的 Telegram 账号。
- 如果怀疑 session 泄露，去 Telegram App 里终止对应登录会话，然后重新生成。

## Contact

如果你在使用过程中遇到问题，欢迎联系我：

- Telegram: [@suversal](https://t.me/suversal)
- Email: `suyloveslife@gmail.com`
