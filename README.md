# HDHive 网页签到 · 历史实现

通过 Playwright 模拟网页登录和签到，不接入验证码服务。触发额外验证时可能无法完成。

## 当前分支与使用入口

| 分支 | 用途 | 入口 |
| --- | --- | --- |
| `codex/shike-backend` | 拾刻 Web 面板：扫码接入、浏览器配置、定时任务和回复记录 | [Web 部署与使用](https://github.com/suversal/hdhive-auto-checkin/tree/codex/shike-backend) |
| `telethon` | Telegram 脚本入门版：配置 JSON 后由 GitHub Actions 定时运行 | [Actions 入门指南](https://github.com/suversal/hdhive-auto-checkin/tree/telethon) |
| `main` | 历史网页签到实现，不处理额外图形验证，不再作为新用户入口 | [main](https://github.com/suversal/hdhive-auto-checkin/tree/main) |
| `feature_yescaptcha` | 历史验证码实验，实现保留但通过率不稳定，不再维护 | [YesCaptcha 分支](https://github.com/suversal/hdhive-auto-checkin/tree/feature_yescaptcha) |

本文下方保留的是**当前历史分支**的原操作说明，不适用于拾刻 Web 面板。不要把网页账号密码、Telegram 用户会话和面板管理密码混用。


---

## ✨ 核心特性

- 🔄 **多账号支持**：支持配置多个账号，按顺序依次执行签到，互不干扰。
- 🎲 **多模式签到**：支持 `daily`（常规每日签到）和 `gamble`（赌狗签到）两种模式。
- ☁️ **开箱即用的 CI**：内置 GitHub Actions 工作流，支持定时自动执行和手动触发。
- 📢 **结果通知**：支持集成 Telegram Bot，签到结束后汇总并推送详细结果。
- 🛡️ **异常捕获与排障**：运行失败时，会自动将网页截图和浏览器诊断 JSON 保存到 Artifacts 中，极大降低排错成本。
- 🕵️ **反指纹侦测**：保留浏览器指纹相关设置，不保证绕过站点验证。

---

## 🚀 部署指引 (GitHub Actions)

以下仅说明历史脚本的 GitHub Actions 用法，无需自备服务器；用量、限制以你自己的 GitHub 账户为准。新用户请先看上方 Web / Telegram 脚本入口。

### 1. Fork 本仓库
点击 `Fork`，取消勾选“Copy the … branch only”，确保包含 **`main`** 分支。然后在自己仓库的 **Settings → General → Default branch** 设为 **`main`**；仅切换页面显示分支不会改变定时任务执行的分支。不要把本历史脚本的密钥填到 Web 面板配置里。

### 2. 配置 Secrets 和 Variables
在你的仓库页面，进入 **Settings** -> **Secrets and variables** -> **Actions**。

#### 🔐 添加 Repository Secrets (机密信息，不可见)
- `HDHIVE_ACCOUNTS_JSON` **(必填)**: 你的 HDHive 账号配置，格式要求为 JSON 数组。
- `TELEGRAM_BOT_TOKEN` (可选): 如果你需要 Telegram 推送，填入你的 Bot Token。

**`HDHIVE_ACCOUNTS_JSON` 配置示例：**
```json
[
  {
    "username": "user1@example.com",
    "password": "password1",
    "sign_type": "daily",
    "telegram_chat_id": "123456789"
  },
  {
    "username": "user2@example.com",
    "password": "password2",
    "sign_type": "gamble",
    "telegram_chat_id": "123456789"
  }
]
```
*优先级说明：账号内配置的 `sign_type` 和 `telegram_chat_id` 会覆盖全局配置。*

#### 🌐 添加 Repository Variables (普通变量，可见)
- `HDHIVE_SIGN_TYPE` (可选，如在HDHIVE_ACCOUNTS_JSON配置则无需再配置): 全局默认签到类型，可选值为 `daily` 或 `gamble`（默认 `daily`）。
- `TELEGRAM_CHAT_ID` (可选，如在HDHIVE_ACCOUNTS_JSON配置则无需再配置): 全局默认的 Telegram 接收人 Chat ID。

### 3. 启用并触发 Actions 工作流
1. 进入 **Actions** 标签页启用工作流，手动运行选择 **`main`** 分支；先配好所需 Secrets，再确认执行。
2. 在左侧边栏点击 **HDHive Check-in**。
3. 点击右侧的 `Run workflow` 手动执行一次，检查是否配置成功。
4. 默认设定的定时任务为北京时间每天 **05:23** 自动执行 (`cron: "23 21 * * *"` 对应 UTC 时间)。
<img width="1983" height="650" alt="image" src="https://github.com/user-attachments/assets/cfa65129-f786-4adc-86c9-bcb8c592eeeb" />

---

## 💻 本地运行与开发

本地运行时，脚本会优先读取仓库根目录下的 `local.config.json`，无需繁琐地去配置环境变量。（该文件已加入 `.gitignore`，仍请在提交前检查暂存区）

### 环境准备

1. 要求 **Python 3.10+**
2. 复制配置文件模板并完善你的账号信息：
   ```bash
   cp local.config.example.json local.config.json
   ```

### 依赖安装与执行

```bash
# 创建并激活虚拟环境 (推荐)
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
python -m pip install -r requirements.txt

# 安装 Playwright 对应的 Chromium 浏览器内核
playwright install chromium

# 运行脚本
python scripts/checkin.py
```

如果你使用 `local.config.json`，通常不需要再手动导出账号相关环境变量。

如果浏览器不在默认位置，可以指定：

```bash
export HDHIVE_BROWSER_PATH="/path/to/chrome"
```

常用环境变量：

- `HDHIVE_BASE_URL`：默认 `https://hdhive.com`
- `HDHIVE_SIGN_TYPE`：默认签到类型
- `HDHIVE_HEADLESS`：默认 `true`
- `HDHIVE_TIMEZONE`：默认 `Asia/Shanghai`
- `HDHIVE_MAX_ATTEMPTS`：每个账号最大尝试次数，默认 `3`
- `HDHIVE_RETRY_BASE_DELAY_SECONDS`：重试基础等待秒数，默认 `5`，按尝试次数线性递增
- `HDHIVE_RESPONSE_BODY_TIMEOUT_SECONDS`：读取签到接口响应 body 的最长等待秒数，默认 `15`
- `TELEGRAM_BOT_TOKEN`：Telegram Bot Token
- `TELEGRAM_CHAT_ID`：默认 Telegram Chat ID

本地文件与环境变量的优先级：

1. `local.config.json`
2. 环境变量
3. 代码默认值

## GitHub Actions

工作流文件是 `.github/workflows/checkin.yml`。

默认行为：

- 使用 `ubuntu-latest`
- 通过 Playwright 驱动 Chrome 执行 `python scripts/checkin.py`
- 支持 `workflow_dispatch`
- 默认 `cron` 为 `23 21 * * *`
- job 总超时为 25 分钟，签到 step 超时为 22 分钟，避免异常挂起占满 GitHub Actions 默认上限

`23 21 * * *` 对应北京时间 `05:23`。

如果你想调整执行时间，直接修改 `.github/workflows/checkin.yml` 里的 `cron`。

GitHub 的定时任务只在默认分支运行，可能延迟；Fork 后需手动启用，公共仓库长期无活动还可能自动停用。见[定时触发说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。从旧脚本迁移到 Telegram 脚本或 Web 面板时，先停用旧计划，避免重复签到。

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
- 失败场景下的浏览器诊断 JSON
- GitHub Actions Summary 表格
- GitHub Actions Artifact：`hdhive-artifacts`

## Notes

- GitHub Actions 下不要依赖 Playwright 自带 `Chromium`
- 当前工作流使用 Playwright 的 `chrome` 渠道，并把失败时的浏览器诊断一并上传
- 本地成功而 GitHub 失败时，优先对比 artifact 中的截图和诊断 JSON

## Example
- 执行日志
<img width="1502" height="570" alt="image" src="https://github.com/user-attachments/assets/7431fb09-363f-4ba6-a3f9-3236620ac6b8" />

- Telegram通知
<img width="284" height="542" alt="image" src="https://github.com/user-attachments/assets/21166a1f-dfba-4260-a82a-21fa75ff52be" />

## Contact

如果你在使用过程中遇到问题，欢迎联系我：

- Telegram: [@suversal](https://t.me/suversal)
- Email: `suyloveslife@gmail.com`
