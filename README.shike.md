# 拾刻 Telegram 自动任务系统

拾刻是一个开源自部署的 Telegram 自动任务面板。通过浏览器接入账号、配置消息和按钮步骤、安排执行时间、查看原始回复和执行记录。根目录原有 README、`scripts/`、`requirements.txt` 和签到工作流继续作为独立的 GitHub Actions 入门方案。

开发计划和验收进度见 [开发计划](docs/development-plan.md)。交互设计原稿保留在 `designs/telegram-console/`，正式前端在 `web/`，真实后端在 `shike/`。

## 本地启动

支持 Python 3.11 及以上的 macOS 和 Linux。Windows 可使用 Docker。新服务使用独立环境，不覆盖原脚本环境：

```bash
python3.11 -m venv .venv-shike
source .venv-shike/bin/activate
python -m pip install -r server/requirements.txt
python -m shike init-admin
python -m shike serve --open
```

首次运行 `init-admin` 时，在终端输入并确认管理密码，输入不会回显。浏览器只提供登录，不开放注册，也不再使用首次设置口令。已有管理员再次执行初始化不会覆盖密码。
已启动服务但浏览器没有打开时，可在同一数据目录运行：

```bash
python -m shike open
```

日常访问默认地址 `http://127.0.0.1:8787`，使用管理密码登录，登录有效期为 24 小时。

## Docker 部署

推荐从 Release 下载 `shike-docker-版本号.zip`，解压后在目录运行：

```bash
sh shike.sh install
```

脚本自动创建配置、拉取镜像，在终端提示设置管理密码，然后启动并显示登录入口。普通电脑和 ARM64 NAS 均有对应镜像，不需要安装 Python 或 Node。首次发布前、尚无公开镜像时，可使用下面的源码构建覆盖文件：

```bash
docker compose -f compose.yaml -f compose.build.yaml build
docker compose -f compose.yaml -f compose.build.yaml run --rm --no-deps shike python -m shike init-admin
docker compose -f compose.yaml -f compose.build.yaml up -d --wait
```

默认只将 8787 端口发布到本机。远端服务器先使用 SSH 转发；有域名时，在 `.env` 填写 `SHIKE_DOMAIN`，脚本可自动启用 Caddy HTTPS。已有反向代理时使用 `SHIKE_PUBLIC_URL`。详细操作、NAS / Windows 用法及排错见 [小白安装与升级指南](docs/docker-deployment.md)。镜像发布及首次公开设置见 [发布指南](docs/releasing.md)。

## 接入 Telegram

1. 前往 [my.telegram.org/apps](https://my.telegram.org/apps) 创建应用，获得 API ID 和 API Hash，在面板中配置。
2. 添加账号时，默认使用扫码登录：手机 Telegram → 设置 → 设备 → 连接桌面设备，扫描并确认。二维码过期会自动刷新。
3. 也可改用手机号验证码，或导入自己已有的 Telethon StringSession。
4. 若账号开启了 Telegram 两步验证，扫码或验证码验证后继续输入两步验证密码。

验证码和两步验证密码不写入数据库；完成授权的会话在服务端加密保存。API Hash 和可选通知 Bot Token 同样加密保存。页面不会回显已保存的凭证。

服务器需要能连接 Telegram。可在“设置 → Telegram 连接”配置 SOCKS5 或 HTTP 代理，保存后测试。代理地址必须是服务器或容器能访问的地址；容器中的 `127.0.0.1` 指容器本身。

账号接入后，可随时在账号卡片点击“编辑名称”修改拾刻内的备注名，无需重新登录 Telegram。任务中的账号显示会同步更新。

## 创建和执行任务

通过四步向导选择方式、执行账号和目标、操作内容、时间和通知。支持发送文字、等待回复、间隔等待和按文字点击当前消息中的按钮。按钮必须唯一匹配；不会自动打开链接、分享联系人或位置。

目标会话支持搜索最近会话，或输入 @用户名、数字 ID。“发给自己”就是 Telegram 自带的 Saved Messages（已保存的消息/收藏夹），只有当前账号本人可见。发送前会列出账号、目标地址、消息条数与内容。

新建普通消息任务默认只发送，Telegram 确认发送后即结束。给个人、群组或收藏夹发消息，不需要对方回复。需要获取机器人签到、查询结果时，在“操作内容”开启“等待对方回复”，或使用带回复步骤的模板；按钮流程会保留必要的等待步骤。已有任务保留原配置，若只需发送，在编辑时关闭等待开关即可。

任务、执行记录、概览和任务详情的列表会直接展示原始回复；表格使用独立回复列，超出列宽时显示省略号，悬停或聚焦可查看全文。执行记录支持搜索任务、回复内容和异常原因。

“等待回复”收到回复后继续，超时则停止；“间隔等待”只是等待指定秒数，不要求对方回复。消息中可插入 `{{date}}`、`{{time}}`、`{{weekday}}`，执行时按任务时区替换。其他花括号保持原样。执行记录保存替换后的实际消息内容。

任务时间支持每日、每周、固定小时间隔、单次和五字段 Cron，并使用任务自己的 IANA 时区。后端返回未来执行时间；设置随机延迟后，实际执行时刻在计划时间之后的指定窗口内。

“创建并开启”只保存后续计划。立即执行需要单独确认真实发送内容。同一账号的任务按顺序执行，同一任务的手动和定时触发互斥。

任务列表可勾选多个任务，批量暂停或开启。每批最多 100 项，确认前会列出影响范围；后端任一项校验失败时不会部分修改。Command/Ctrl + K 可搜索任务并跳转常用页面。

执行记录会保留发送状态、步骤日志、原始回复、耗时、业务规则匹配结果和通知结果。“已收到回复”不等同于业务成功；仅在命中用户填写的规则时显示匹配成功或失败，失败关键词优先。

等待回复超时时，记录显示“已发送 · 未等到回复”，表示 Telegram 已确认消息发送，但在设定时间内没收到符合条件的回复。对方可能已经处理，服务不会自动重发。发送请求结果不确定时，记录显示“发送结果未确认”。服务重启会标记未完成记录为中断，跳过过期计划，恢复后续计划，避免集中补发。Telegram 限流等待时间按账号保存，后续调度会尊重该限制。

空闲连接在下一次使用前会刷新；网络异常后丢弃失效连接，后续任务重新建立连接。连接恢复不会自动重放失败或发送结果不确定的业务操作。

## 通知和模板

支持仅异常、每次执行、每日摘要或不通知。默认使用执行账号的收藏夹；可配置独立机器人发送通知。通知失败不会改变业务执行结果，也不会触发业务消息重发。

导出模板不包含账号会话和 Token。导入时由服务端校验，任务默认暂停；确认自己的账号、目标和时间后再开启。

## 数据和升级

本地默认数据目录为 `var/shike/`，可使用 `SHIKE_DATA_DIR` 指定。Docker 为 `/data` 命名卷。目录中包括 SQLite 数据库和加密密钥 `master.key`。数据库与密钥必须一起保留；只复制数据库而丢失密钥会无法解密账号。

推荐使用管理脚本，先备份再升级，目标版本替换成实际已发布版本：

```bash
sh shike.sh backup
sh shike.sh upgrade 0.1.1
# 如需切回上次镜像，保留当前数据库：
sh shike.sh rollback
```

升级命令自带备份步骤，手动执行 backup 是可选的。维护时禁止新任务，有任务执行则稍后再试；新镜像启动失败时先尝试原镜像，不自动覆盖数据库。备份包括 SQLite 一致性快照、原密钥和 `.env`。手动恢复备份后所有任务暂停，防止重复发送。完整恢复步骤见部署指南。

保留原数据卷、`.env` 与安装目录名；不要执行 `docker compose down -v`。默认保留 30 天执行记录，可在设置中改为 7 或 90 天。服务要求单实例、单 worker，共用一个数据目录的第二个实例会拒绝启动。

忘记管理密码时，先停止服务，再在相同数据目录、相同密钥环境下执行：

```bash
python -m shike reset-password
# Docker 停止服务后可使用同一卷运行：
docker compose run --rm --no-deps shike python -m shike reset-password
```

重置只修改面板管理密码并撤销旧管理登录，不会删除 Telegram 会话和任务。

## 开发验证

```bash
python -m pip install -r server/requirements-dev.txt
python -m pytest server/tests -q
TELEGRAM_LOCAL_CONFIG_PATH=/tmp/shike-no-local-config.json python -m unittest discover -s tests
cd web && npm ci && npm run build
```

后端测试使用进程内注入的 Telegram 测试适配器，覆盖真实的 HTTP、数据库、调度、加密和状态流转；生产入口没有切换到模拟账号的环境变量。实号登录和真实消息送达另行验收，不以测试适配器结果替代。

前端使用 React、Radix、cmdk 和 React DayPicker，本地打包后不依赖 CDN。`calendar.css`、`app.js` 与 `THIRD_PARTY_NOTICES.txt` 由构建生成。第二轮功能对比和界面检查见 [优化记录](docs/refinement-round-2.md)。
