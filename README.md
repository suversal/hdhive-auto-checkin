<div align="center">
  <h1>🚨 HDHive Auto Check-in 🚨</h1>
  <p><b>基于 `Python + Playwright` 编写的 HDHive 自动化签到工具</b></p>
  <p><b>由于 HDHive 站点使用了 Next.js Server Actions，其请求头中包含了动态的 `Next_Action` 校验参数，使用传统的纯 HTTP 请求（如 requests/curl）进行模拟非常繁琐且易失效，需要频繁抓包修改配置。故新版本通过 Playwright 驱动真实浏览器进行自动化操作，完美绕过动态参数校验，实现更加稳定的自动化签到。</b></p>
  <h3>👉 <a href="https://github.com/suversal/auto-check">旧版方案地址：HDHive自动化签到工具 (传统HTTP请求版 需手动维护ActionId)</a> 👈</h3>
  <br/>
</div>


---

## ✨ 核心特性

- 🔄 **多账号支持**：支持配置多个账号，按顺序依次执行签到，互不干扰。
- 🎲 **多模式签到**：支持 `daily`（常规每日签到）和 `gamble`（赌狗签到）两种模式。
- ☁️ **开箱即用的 CI**：内置 GitHub Actions 工作流，支持定时自动执行和手动触发。
- 📢 **结果通知**：支持集成 Telegram Bot，签到结束后汇总并推送详细结果。
- 🛡️ **异常捕获与排障**：运行失败时，会自动将网页截图和浏览器诊断 JSON 保存到 Artifacts 中，极大降低排错成本。
- 🕵️ **反指纹侦测**：内置浏览器指纹混淆脚本，有效降低被站点防火墙拦截的概率。

---

## 🚀 部署指引 (GitHub Actions)

推荐使用 GitHub Actions 进行部署，无需自备服务器，完全免费。

### 1. Fork 本仓库
点击页面右上角的 `Fork` 按钮，将本项目 Fork 到你自己的 GitHub 账号下。

### 2. 配置 Secrets 和 Variables
在你的仓库页面，进入 **Settings** -> **Secrets and variables** -> **Actions**。

#### 🔐 添加 Repository Secrets (机密信息，不可见)
- `HDHIVE_ACCOUNTS_JSON` **(必填)**: 你的 HDHive 账号配置，格式要求为 JSON 数组。
- `TELEGRAM_BOT_TOKEN` (可选): 如果你需要 Telegram 推送，填入你的 Bot Token。

**`HDHIVE_ACCOUNTS_JSON` 配置示例：**
```json
[
  {
    "name": "主账号",
    "username": "user1@example.com",
    "password": "password1",
    "sign_type": "daily",
    "telegram_chat_id": "123456789"
  },
  {
    "name": "小号",
    "username": "user2@example.com",
    "password": "password2",
    "sign_type": "gamble"
  }
]
```
*优先级说明：账号内配置的 `sign_type` 和 `telegram_chat_id` 会覆盖全局配置。*

#### 🌐 添加 Repository Variables (普通变量，可见)
- `HDHIVE_SIGN_TYPE` (可选): 全局默认签到类型，可选值为 `daily` 或 `gamble`（默认 `daily`）。
- `TELEGRAM_CHAT_ID` (可选): 全局默认的 Telegram 接收人 Chat ID。

### 3. 启用并触发 Actions 工作流
1. 进入 **Actions** 标签页，点击 `I understand my workflows, go ahead and enable them`。
2. 在左侧边栏点击 **HDHive Check-in**。
3. 点击右侧的 `Run workflow` 手动执行一次，检查是否配置成功。
4. 默认设定的定时任务为北京时间每天 **00:05** 自动执行 (`cron: "5 16 * * *"` 对应 UTC 时间)。

---

## 💻 本地运行与开发

本地运行时，脚本会优先读取仓库根目录下的 `local.config.json`，无需繁琐地去配置环境变量。（该文件已加入 `.gitignore`，不会被误提交）

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
- 失败场景下的浏览器诊断 JSON
- GitHub Actions Summary 表格
- GitHub Actions Artifact：`hdhive-artifacts`

## Notes

- GitHub Actions 下不要依赖 Playwright 自带 `Chromium`
- 当前工作流使用 `browser-actions/setup-chrome` 安装 `Chrome for Testing`
- 当前工作流还会通过 `xvfb-run` 启动非 headless Chrome，并把失败时的浏览器诊断一并上传
- 本地成功而 GitHub 失败时，优先对比 artifact 中的截图和诊断 JSON
