# 拾刻本地开发

正式使用建议先看[项目首页](../README.md)和 [Docker 部署指南](docker-deployment.md)。此页用于直接运行源码和验证修改；原 GitHub Actions 脚本独立使用根目录的 `requirements.txt`。

## 启动后端

macOS / Linux 使用 Python 3.11 及以上，Windows 可使用 Docker 或 WSL。新服务使用独立环境：

```bash
git clone --branch codex/shike-backend https://github.com/suversal/hdhive-auto-checkin.git shike
cd shike
python3.11 -m venv .venv-shike
source .venv-shike/bin/activate
python -m pip install -r server/requirements.txt
python -m shike init-admin
python -m shike serve --open
```

管理密码在终端输入并确认，输入不回显。已有管理员再次初始化不会覆盖密码。浏览器使用 `http://127.0.0.1:8787`，登录有效期为 24 小时。服务已经运行时，在同一目录执行 `python -m shike open` 可重新打开页面。

## 构建前端

使用 Node.js 22 和 npm，在仓库根目录运行：

```bash
npm ci --prefix web
npm run build --prefix web
```

前端使用 React、Radix、cmdk 和 React DayPicker。源码在 `web/`，打包后不依赖 CDN。`app.js`、`index.html`、`calendar.css` 和 `THIRD_PARTY_NOTICES.txt` 随构建更新，修改界面后一起提交。

## 数据和进程

默认数据目录为 `var/shike/`，可用 `SHIKE_DATA_DIR` 指定。SQLite 数据库和 `master.key` 必须一起保留，丢失密钥会无法解密账号。更改目录前先停止服务并完整备份；同一个数据目录只允许单实例、单 worker。

忘记管理密码时，停止服务后，在相同目录和密钥环境下运行 `python -m shike reset-password`，然后重新启动。这会撤销旧面板登录，保留 Telegram 会话和任务。

## 修改后的检查

按修改范围选择适用检查：

```bash
python -m pip install -r server/requirements-dev.txt
python -m pytest server/tests -q
TELEGRAM_LOCAL_CONFIG_PATH=/tmp/shike-no-local-config.json python -m unittest discover -s tests
npm ci --prefix web
npm run build --prefix web
sh -n shike.sh
```

后端测试使用进程内注入的 Telegram 测试适配器，覆盖 HTTP、数据库、调度、加密和状态流转，不会登录真实账号或发送真实消息。生产入口没有切换到模拟账号的环境变量。实号登录和消息送达需要单独验证。

设计原稿在 `designs/telegram-console/`，后端在 `shike/`。另见[开发计划](development-plan.md)、[优化记录](refinement-round-2.md)和[镜像发布流程](releasing.md)。
