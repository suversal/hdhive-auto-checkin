# HDHive Auto Check-in

使用 `Python + Playwright` 自动登录 HDHive 并执行签到，避免手动维护动态 `Next_Action`。

## Features

- 支持多个账号顺序签到
- 支持 `daily` 和 `gamble` 两种签到模式
- 支持 GitHub Actions 定时执行和手动触发
- 支持 Telegram 结果通知
- 失败时自动保存截图和结果 JSON

## Repository Layout

- `scripts/checkin.py`：签到主脚本
- `.github/workflows/checkin.yml`：GitHub Actions 工作流
- `requirements.txt`：Python 依赖
- `artifacts/`：结果文件和失败截图目录

## Configuration

### GitHub Secrets

- `HDHIVE_ACCOUNTS_JSON`
- `TELEGRAM_BOT_TOKEN`，可选

### GitHub Variables

- `HDHIVE_SIGN_TYPE`，可选，默认签到类型，支持 `daily` 或 `gamble`
- `TELEGRAM_CHAT_ID`，可选，默认 Telegram 接收人

### `HDHIVE_ACCOUNTS_JSON` Example

```json
[
  {
    "name": "main",
    "username": "user1@example.com",
    "password": "password1",
    "sign_type": "daily",
    "telegram_chat_id": "123456789"
  },
  {
    "name": "backup",
    "username": "user2@example.com",
    "password": "password2",
    "sign_type": "gamble"
  }
]
```

字段说明：

- `name`：通知里显示的账号别名，可选
- `username`：HDHive 登录账号，必填
- `password`：HDHive 登录密码，必填
- `sign_type`：签到类型，可选，支持 `daily` 或 `gamble`
- `telegram_chat_id`：单账号 Telegram Chat ID，可选

优先级：

- 账号内 `sign_type` 覆盖全局 `HDHIVE_SIGN_TYPE`
- 账号内 `telegram_chat_id` 覆盖全局 `TELEGRAM_CHAT_ID`

## Local Run

建议本地优先使用 Chrome：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export HDHIVE_ACCOUNTS_JSON='[{"username":"your@example.com","password":"your-password","sign_type":"daily"}]'
python scripts/checkin.py
```

如果浏览器不在默认位置，可以指定：

```bash
export HDHIVE_BROWSER_PATH="/path/to/chrome"
```

常用环境变量：

- `HDHIVE_BASE_URL`：默认 `https://hdhive.com`
- `HDHIVE_SIGN_TYPE`：默认签到类型
- `HDHIVE_HEADLESS`：默认 `true`
- `HDHIVE_TIMEZONE`：默认 `Asia/Shanghai`
- `TELEGRAM_BOT_TOKEN`：Telegram Bot Token
- `TELEGRAM_CHAT_ID`：默认 Telegram Chat ID

## GitHub Actions

工作流文件是 `.github/workflows/checkin.yml`。

默认行为：

- 使用 `ubuntu-latest`
- 安装 `Chrome for Testing`
- 通过 `xvfb-run` 以非 headless 方式执行 `python scripts/checkin.py`
- 支持 `workflow_dispatch`
- 默认 `cron` 为 `5 16 * * *`

`5 16 * * *` 对应北京时间 `00:05`。

如果你想调整执行时间，直接修改 `.github/workflows/checkin.yml` 里的 `cron`。

## Telegram Notification

设置 `TELEGRAM_BOT_TOKEN` 后，脚本会自动推送结果通知。

通知内容包括：

- 执行时间
- 站点地址
- 成功 / 已签 / 失败 / 未知统计
- 每个账号的签到类型、状态和说明
- 失败账号的截图路径

## Outputs

每次执行后会生成：

- `artifacts/latest-results.json`
- 失败场景下的截图 PNG
- GitHub Actions Summary 表格
- GitHub Actions Artifact：`hdhive-artifacts`

## Notes

- GitHub Actions 下不要依赖 Playwright 自带 `Chromium`
- 当前工作流使用 `browser-actions/setup-chrome` 安装 `Chrome for Testing`
- 当前工作流还会通过 `xvfb-run` 启动非 headless Chrome，并附带额外启动参数
- 这样更容易绕过 HDHive 对默认自动化环境的识别
