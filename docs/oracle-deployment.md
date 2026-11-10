# 甲骨文拾刻部署记录

部署日期：2026 年 11 月 10 日（北京时间）。

## 当前实例

- 目标：SSH 别名 `oracle-blog`，ARM64 Linux。
- 入口：`https://shike.suversal.com/`。
- 应用提交：`4bdd0b59495606058e2e673918985ca503577a5a`，版本 `0.1.0`。
- 构建方式：从已提交源码在服务器构建，镜像为 `ghcr.io/suversal/hdhive-auto-checkin:local-4bdd0b5`。这个标签仅存在于服务器，不表示已向 GHCR 发布。
- 目录：`/home/ubuntu/shike`；独立 Compose 项目 `shike`、数据卷 `shike_shike-data`。
- 后端仅监听 `127.0.0.1:8787`；`.env` 的公开来源为 `https://shike.suversal.com`，Secure Cookie 开启。
- 按用户选择新建空实例，未迁移本机账号、任务、记录或管理密码。验收时账号、任务和记录均为 0。

## 域名与 HTTPS

Cloudflare 新增了拾刻专用的代理 DNS 记录。源站复用服务器现有的 Caddy 网关与通配 Origin 证书，只追加拾刻站点，转发到本机 8787。

本机已有统一网关，**不要在这个实例叠加 `compose.https.yaml` 再启动第二个 Caddy**。现有 Caddy 配置在校验、备份后使用 `SIGUSR1` 平滑重载，没有重启网关容器。备份路径保存在服务器的 `.shike/gateway-backup-path` 中，原有站点配置保持不变。

## 首次使用

网页只提供管理密码登录，首次设置口令和公开注册已移除。云端管理密码由用户本人在服务器终端设置一次，后续不同设备使用同一密码登录。

在自己电脑的终端运行：

```bash
ssh -t oracle-blog 'cd /home/ubuntu/shike && sudo -n sh shike.sh init'
```

按提示输入两遍至少 10 位的管理密码，输入不回显。命令先检查活动执行，安全暂停拾刻，设置后恢复服务；已有管理员时保留原密码。完成后打开 `https://shike.suversal.com/`，刷新并用管理密码登录，再按页面引导填写 Telegram API 信息和接入账号。

只有管理密码遗忘时才运行 `sudo -n sh shike.sh reset-password`；这会撤销旧面板登录，保留 Telegram 会话和任务。不要把密码发到聊天、公开文档或命令参数中。

## 日常维护

```bash
ssh oracle-blog
cd /home/ubuntu/shike
sudo -n sh shike.sh status
sudo -n sh shike.sh logs
sudo -n sh shike.sh backup
```

安装目录的 `.env`、`.shike`、`backups` 和数据卷都需要保留，不要执行 `docker compose down -v`。

正式镜像发布后，可使用实际发布的版本号升级：

```bash
sudo -n sh shike.sh upgrade 实际版本号
```

升级脚本会先备份，再更换镜像，保留此实例的数据卷和外部 HTTPS 来源。当前源码镜像标签尚未公开，省略版本号不能从 GHCR 拉取这个本地标签。若继续源码构建，先按维护流程备份，在没有活动任务时更新源码，再使用构建覆盖文件；不要覆盖现有 `.env`。

同一 Telegram 任务只在一个地方开启。启用云端任务前，核对本机测试实例和旧 Actions 是否还在执行相同任务。

公网静态文件带有 Cloudflare 浏览器缓存。新构建的首页会为 JS 和 CSS 附带内容版本标记，避免升级后复用旧登录流程。旧页面仍显示时刷新首页；API 响应使用 `no-store`。

## 验收与范围

- 服务通过 Docker 健康检查，非 root 用户 UID 10001 运行。
- 数据目录权限 700，加密密钥文件权限 600。
- 公网 HTTPS 健康接口返回 200，Chrome 正常加载新版单密码登录页。源站未登录读取 `/api/state`、`/api/settings` 为 401，公开初始化和注册接口均为 404；首页与三项带内容版本标记的静态资源通过 SHA256 对照。
- Telegram 默认数据中心 TCP 连接可达；未配置真实账号，因此没有执行 Telegram 登录或发送消息。
- 现有 13 个容器的 ID 和启动时间均保持不变，没有触发 AIRadar / SourcePilot 采集或其他业务任务。
- 首次构建发现私有源码归档权限导致应用文件不可读，已通过 Dockerfile 固定代码可读权限解决；CI 增加严格源码权限场景，修复后的 GitHub CI 全部通过。

这里只完成部署和登录入口交付，管理密码、Telegram API 配置、扫码和实号发送由用户后续完成。未创建正式 Release，也未将本地账号数据上传服务器。

## 取消首次设置口令后的更新

应用提交 `4bdd0b5` 已备份升级。升级前备份目录为 `/home/ubuntu/shike/backups/20261110T134436Z-3933276`，原数据卷、加密密钥权限及已有服务运行状态保持不变。验收时管理员仍未创建，账号、任务、活动执行均为 0，维护模式已退出。用户选择自己在服务器终端创建管理密码，命令见“首次使用”。

[该提交的 GitHub CI](https://github.com/suversal/hdhive-auto-checkin/actions/runs/42827094139) 的 service、legacy、docker 三项全部通过。服务器仍使用本地源码镜像，未创建公开 Release。
