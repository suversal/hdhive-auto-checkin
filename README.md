<div align="center">
  <h1>🧩 HDHive Telegram 自动签到 🧩</h1>
  <p><b>基于 `Python + Telethon + GitHub Actions` 编写的 HDHive 自动化签到工具</b></p>
  <p><b>当前定位：推荐使用的 HDHive 自动签到方案，不访问 HDHive 网页，也不依赖 Playwright 点击签到按钮。</b></p>
  <p><b>工作方式：通过 Telegram 用户会话向已绑定 HDHive 账号的机器人发送 <code>赌狗签到</code>，再解析机器人回复生成结果通知。</b></p>
  <p><b>推荐原因：实测 YesCaptcha 网页图形点选验证通过率不稳定，Telegram 机器人路线可以绕开网页端验证码问题。</b></p>
  <h3>👉 <a href="https://github.com/suversal/hdhive-auto-checkin/tree/main">telegram绑定签到（V3版本 前推荐方案）：telethon分支 </a> 👈</h3>
  <h3>👉 <a href="https://github.com/suversal/hdhive-auto-checkin/tree/feature_yescaptcha">使用yescaptcha进行签到验证（V2版本 成功率较低 不推荐使用 可自行fork优化）：feature_yescaptcha分支</a> 👈</h3>
  <h3>👉 <a href="https://github.com/suversal/hdhive-auto-checkin/tree/main">网页端签到分支（V1版本 无签到验证时使用 不再维护）：main分支</a> 👈</h3>
  <br/>
</div>

---

## ✨ 核心特性

- 🔄 **多账号支持**：支持多个 Telegram 账号，每个账号使用自己的 `session`。
- 🎲 **机器人签到**：向 HDHive Telegram 机器人发送 `赌狗签到`，不再依赖网页端签到按钮。
- ☁️ **开箱即用的 CI**：内置 GitHub Actions 工作流，支持定时自动执行和手动触发。
- 📢 **结果通知**：支持每个账号给自己发送单独通知，也支持主账号接收所有账号汇总通知。
- 🧾 **结果留档**：会保存执行结果到 `artifacts/latest-results.json`，并写入 GitHub Actions Summary。
- 🔐 **安全配置**：敏感信息通过 GitHub Secrets 管理，本地配置文件默认不会提交。

---

## 工作流程

1. GitHub Actions 到点运行。
2. 脚本读取 Telegram API 信息和账号配置。
3. 每个账号使用自己的 Telethon `StringSession` 登录 Telegram。
4. 脚本向 HDHive 机器人发送 `赌狗签到`。
5. 等待机器人回复。
6. 解析回复内容：
   - `签到成功，获得 x 积分`
   - `你已经签到过了，明天再来吧`
   - 失败或未知回复
7. 给每个账号发送自己的通知。
8. 给主账号发送所有账号汇总通知。
9. 保存结果文件。

## 准备工作

你需要准备下面几样东西：

- 一个 GitHub 仓库，用来运行 GitHub Actions。
- 一个 Telegram 账号，并且这个账号已经和 HDHive 机器人绑定。
- Telegram API 的 `api_id` 和 `api_hash`。
- 每个 Telegram 账号对应的 `TELEGRAM_SESSION`。
- HDHive 机器人的 Telegram username，例如 `@HDHiveBot`。实际名称以你的机器人资料页为准。

## 获取 Telegram api_id 和 api_hash

1. 打开 [my.telegram.org/apps](https://my.telegram.org/apps)。
2. 使用你的 Telegram 手机号登录。
3. 点击创建 application。
4. 表单建议这样填：

```text
App title: HDHive Auto Checkin
Short name: hdhivecheckin
URL: https://github.com/suversal
Platform: Desktop
Description: Personal Telegram automation for HDHive checkin
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

编辑 `local.config.json`。一个账号时：

```json
{
  "telegram_api_id": "123456",
  "telegram_api_hash": "your-api-hash",
  "telegram_response_timeout_seconds": "60",
  "telegram_summary_notify_chat_id": "me",
  "hdhive_telegram_accounts_json": [
    {
      "name": "account-1",
      "session": "first-account-telethon-string-session",
      "bot_username": "@HDHiveBot",
      "command": "赌狗签到",
      "notify_chat_id": "me"
    }
  ]
}
```

两个账号时：

```json
{
  "telegram_api_id": "123456",
  "telegram_api_hash": "your-api-hash",
  "telegram_response_timeout_seconds": "60",
  "telegram_summary_notify_chat_id": "me",
  "hdhive_telegram_accounts_json": [
    {
      "name": "account-1",
      "session": "first-account-telethon-string-session",
      "bot_username": "@HDHiveBot",
      "command": "赌狗签到",
      "notify_chat_id": "me"
    },
    {
      "name": "account-2",
      "session": "second-account-telethon-string-session",
      "bot_username": "@HDHiveBot",
      "command": "赌狗签到",
      "notify_chat_id": "me"
    }
  ]
}
```

字段说明：

- `telegram_api_id`：你在 my.telegram.org 申请到的 `api_id`。
- `telegram_api_hash`：你在 my.telegram.org 申请到的 `api_hash`。
- `telegram_response_timeout_seconds`：等待 HDHive 机器人回复的最长时间，默认 `60` 秒。
- `telegram_summary_notify_chat_id`：主账号接收所有账号汇总通知的目标。
- `hdhive_telegram_accounts_json`：账号数组。一条就是一个账号，两条就是两个账号。
- `name`：账号名称，只用于日志和通知展示，建议写容易识别的名字。
- `session`：该 Telegram 账号生成的 `TELEGRAM_SESSION`。
- `bot_username`：HDHive 机器人的 username，例如 `@HDHiveBot`。
- `command`：发送给机器人的签到命令，通常是 `赌狗签到`。
- `notify_chat_id`：该账号自己的通知目标。

## 通知怎么配置

有两种通知：

### 账号自己的通知

配置在每个账号里：

```json
"notify_chat_id": "me"
```

含义：这个账号签到完成后，把自己的结果发到自己的 Telegram Saved Messages。

### 主账号汇总通知

配置在顶层：

```json
"telegram_summary_notify_chat_id": "me"
```

含义：所有账号执行完后，发送一条汇总通知。

注意：如果这里填 `me`，汇总通知会发到**第一个执行账号**的 Saved Messages，因为脚本使用第一个账号的 session 发送汇总。

如果你想让固定主账号接收汇总，推荐填主账号的 Telegram username 或 chat id，例如：

```json
"telegram_summary_notify_chat_id": "@your_username"
```

`notify_chat_id` 和 `telegram_summary_notify_chat_id` 支持：

- `""`：不发送对应通知。
- `"me"`：发送到当前 session 对应账号的 Saved Messages。
- `"@username"`：发送给指定 Telegram 用户。
- 数字 chat id：发送到指定用户、群组或频道。

## 本地测试

确认当前分支：

```bash
git branch --show-current
```

安装并激活依赖：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

先跑单元测试：

```bash
HDHIVE_LOCAL_CONFIG_PATH=/private/tmp/hdhive-missing-local-config.json python -m unittest discover -s tests
```

预期输出：

```text
Ran 20 tests
OK
```

再跑真实签到：

```bash
python scripts/telegram_checkin.py
```

成功时你会看到类似日志：

```text
[12:00:00] 成功加载 2 个 Telegram 签到账号
[12:00:01] [account-1] 准备向 @HDHiveBot 发送签到命令: 赌狗签到
[12:00:02] [account-1] 签到命令已发送，等待机器人回复...
[12:00:03] [account-1] 机器人回复: 你已经签到过了，明天再来吧
```
<img width="612" height="279" alt="image" src="https://github.com/user-attachments/assets/a25f0848-2918-4d14-aff7-0f01422a20d7" />

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

添加下面三个 Secrets：

```text
TELEGRAM_API_ID
TELEGRAM_API_HASH
HDHIVE_TELEGRAM_ACCOUNTS_JSON
```

注意：不要把整个 `local.config.json` 作为一个 Secret 填进去。GitHub Actions 不会直接读取一个完整的本地配置文件。

你需要把 `local.config.json` 拆成下面几项：

| local.config.json 字段 | GitHub 中填写到哪里 |
| --- | --- |
| `telegram_api_id` | Secret: `TELEGRAM_API_ID` |
| `telegram_api_hash` | Secret: `TELEGRAM_API_HASH` |
| `hdhive_telegram_accounts_json` | Secret: `HDHIVE_TELEGRAM_ACCOUNTS_JSON` |
| `telegram_response_timeout_seconds` | Variable: `TELEGRAM_RESPONSE_TIMEOUT_SECONDS` |
| `telegram_summary_notify_chat_id` | Variable: `TELEGRAM_SUMMARY_NOTIFY_CHAT_ID` |

`HDHIVE_TELEGRAM_ACCOUNTS_JSON` 只填账号数组。不要包含外层对象，也不要包含 `telegram_api_id`、`telegram_api_hash`、`telegram_response_timeout_seconds`、`telegram_summary_notify_chat_id`。

如果你的本地配置是：

```json
{
  "telegram_api_id": "123456",
  "telegram_api_hash": "your-api-hash",
  "telegram_response_timeout_seconds": "60",
  "telegram_summary_notify_chat_id": "me",
  "hdhive_telegram_accounts_json": [
    {
      "name": "account-1",
      "session": "first-account-telethon-string-session",
      "bot_username": "@HDHiveBot",
      "command": "赌狗签到",
      "notify_chat_id": "me"
    }
  ]
}
```

那么 `HDHIVE_TELEGRAM_ACCOUNTS_JSON` 只填这一段：

```json
[
  {
    "name": "account-1",
    "session": "first-account-telethon-string-session",
    "bot_username": "@HDHiveBot",
    "command": "赌狗签到",
    "notify_chat_id": "me"
  },
  {
    "name": "account-2",
    "session": "second-account-telethon-string-session",
    "bot_username": "@HDHiveBot",
    "command": "赌狗签到",
    "notify_chat_id": "me"
  }
]
```

### Variables

添加下面两个 Variables：

```text
TELEGRAM_RESPONSE_TIMEOUT_SECONDS = 60
TELEGRAM_SUMMARY_NOTIFY_CHAT_ID = me
```

如果你不想发送汇总通知，可以不配置 `TELEGRAM_SUMMARY_NOTIFY_CHAT_ID`。

## 触发方式

工作流支持三种触发方式：

- 定时触发：北京时间每天 `06:23`。
- 手动触发：GitHub Actions 页面点击 `Run workflow`。
- push 触发：当 `scripts/**`、`tests/**`、workflow、依赖或配置模板变化时触发。

定时配置在 [.github/workflows/checkin.yml](/Users/sue/hdhive-auto-checkin/.github/workflows/checkin.yml)：

```yaml
cron: "23 22 * * *"
```

这个时间是 UTC，对应北京时间每天 `06:23`。

## 机器人回复如何判断

脚本会解析 HDHive 机器人的回复：

- 包含 `签到成功`：状态为 `success`。
- 包含 `已经签到` 或 `明天再来`：状态也为 `success`，并标记 `already_signed=true`。
- 包含 `失败`：状态为 `failed`。
- 其他内容：状态为 `unknown`。

如果任意账号是 `failed` 或 `unknown`，GitHub Actions 会标记为失败，方便你发现问题。

## 汇总通知格式

汇总通知大致如下：

```text
🧩 HDHive 自动签到
━━━━━━━━━━━━━━━━━━
🕒 执行时间：2026-06-02 07:12:51
🌐 目标站点：https://hdhive.com
📊 统计汇总：成功 2  /失败 0  /未知 0

👥
⎡ 📧 账号：account-1
├ 🏷️ 类型：赌狗签到
⎣ 📝 结果：签到成功，获得 0 积分

👥
⎡ 📧 账号：account-2
├ 🏷️ 类型：赌狗签到
⎣ 📝 结果：你已经签到过了，明天再来吧
```

## 常见问题

### 1. `ModuleNotFoundError: No module named 'telethon'`

没有安装依赖，或当前终端没有激活项目虚拟环境。

执行：

```bash
cd /Users/sue/hdhive-auto-checkin
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. `PasswordHashInvalidError`

Telegram 二步验证密码错误。

这里要输入的是 Telegram 的 Two-Step Verification Password，不是短信验证码。

### 3. `PhoneCodeInvalidError`

验证码错误。重新运行 `generate_telegram_session.py`，输入最新验证码。

### 4. `PhoneCodeExpiredError`

验证码过期。重新运行脚本获取新验证码。

### 5. `Cannot find any entity corresponding to "5795587098"`

通知目标无法解析。发给当前账号自己时，建议填：

```json
"notify_chat_id": "me"
```

### 6. `local.config.json JSON 格式错误`

本地配置不是合法 JSON。常见原因：

- 多粘贴了一段 JSON。
- 少了逗号。
- 字符串没有用双引号。
- JSON 结尾后面还有多余内容。

可以用下面命令检查：

```bash
python -m json.tool local.config.json
```

### 7. GitHub Actions 里没有收到通知

先看 Actions 日志：

- 是否成功读取了账号配置。
- 是否机器人有回复。
- 是否通知发送失败。

如果 `notify_chat_id` 填的是 `me`，每个账号的通知会发到该账号自己的 Saved Messages。

如果 `telegram_summary_notify_chat_id` 填的是 `me`，汇总通知会发到第一个执行账号自己的 Saved Messages。

## 安全说明

`TELEGRAM_SESSION` 等同于 Telegram 登录凭证。任何拿到它的人，都可能用你的 Telegram 账号发消息。

请注意：

- 不要把真实 session 提交到仓库。
- 不要把真实 session 发到 Issue、日志、截图里。
- 建议使用专门绑定 HDHive 机器人的 Telegram 账号。
- 如果怀疑 session 泄露，去 Telegram App 里终止对应登录会话，然后重新生成。

## Contact

如果你在使用过程中遇到问题，欢迎联系我：

- Telegram: [@suversal](https://t.me/suversal)
- Email: `suyloveslife@gmail.com`
