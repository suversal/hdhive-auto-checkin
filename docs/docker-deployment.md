# 拾刻安装、升级与恢复

拾刻提供两种独立用法：不需要网页管理时，使用仓库原有的 GitHub Actions 入门脚本；需要网页配置、扫码接入和执行记录时，使用这里的 Docker 完整版。

## 先准备什么

- 一台能连接 Telegram 的常开电脑、NAS 或 Linux 服务器。
- Docker 和 `docker compose` 插件。Windows / macOS 用户可安装 [Docker Desktop](https://docs.docker.com/get-started/get-docker/)，服务器按 [Docker Engine 官方指南](https://docs.docker.com/engine/install/) 安装。
- 支持 Linux AMD64 和 ARM64。Windows 使用 Linux 容器；脚本命令可在 WSL 终端运行。32 位 ARM 不在镜像支持范围内。

安装过程中不需要在宿主机安装 Python、Node，也不需要手动创建管理密码或 Telegram 配置文件。

## 第一次安装：下载、启动、打开网页

1. 在项目的 **Releases** 页面下载 `shike-docker-版本号.zip`，解压得到 `shike` 文件夹。不要下载 GitHub 自动生成的 Source code 代替安装包。
2. 启动 Docker，在解压文件夹中打开终端，运行：

   ```bash
   sh shike.sh install
   ```

3. 等待出现健康检查通过和网页入口，在自己的浏览器打开该入口，设置管理密码。
4. 根据页面引导填写 Telegram API ID / API Hash，然后扫码接入账号，创建第一条任务。

安装包固定使用对应版本的镜像，不会自动跳到其他版本。默认入口是 `http://127.0.0.1:8787`，只允许本机访问。首次设置入口会带一次性初始化凭证，只在自己的浏览器打开；后续登录只用管理密码。

如果 Releases 尚无安装包、或镜像还未公开，先使用本文末尾的“源码构建”。发布流水线不会因为下载源码就自动执行。

## 装在云服务器：先通过 SSH 打开

服务器上安装完成后，在**你自己的电脑**终端运行，将 `用户名` 和 `服务器地址` 换成实际值：

```bash
ssh -N -L 8787:127.0.0.1:8787 用户名@服务器地址
```

保持该终端开启，然后在自己电脑的浏览器打开安装命令显示的入口。浏览器里的 `127.0.0.1` 指自己的电脑，SSH 会把访问转发到服务器。

若本机 8787 已被占用，可把转发命令第一个端口改为 8789，同时把浏览器入口中的端口改成 8789。

## 有域名：可选自动 HTTPS

1. 将域名的 DNS 记录指向服务器，放行服务器的 TCP 80、443 端口，确认没有其他服务占用它们。
2. 首次运行脚本前，将 `.env.shike.example` 复制为 `.env`；已有 `.env` 时直接编辑，**不要用示例覆盖现有配置**。
3. 只需填写这一项，其他内容保持原样：

   ```dotenv
   SHIKE_DOMAIN=shike.example.com
   ```

4. 运行 `sh shike.sh install`。脚本自动加载 `compose.https.yaml`，由 Caddy 申请证书并转发到后端。之后使用 `https://你的域名`。

证书申请需要域名能从公网解析并访问服务器。Caddy 的证书保存在独立 Docker 卷中，普通升级会保留。

已有 HTTPS 反向代理时，留空 `SHIKE_DOMAIN`，填写 `SHIKE_PUBLIC_URL=https://你的域名`，让现有代理转发到本机 8787 并保留 Host。不要将管理面板直接开放为公网明文 HTTP。暂不支持 `/shike` 等域名子路径。

## 常用命令

在安装文件夹中运行：

| 操作 | 命令 |
| --- | --- |
| 启动或恢复服务 | `sh shike.sh start` |
| 找回设置 / 登录入口 | `sh shike.sh open` |
| 查看健康与运行状态 | `sh shike.sh status` |
| 查看日志，按 Ctrl+C 退出 | `sh shike.sh logs` |
| 备份 | `sh shike.sh backup` |
| 升级到指定已发布版本 | `sh shike.sh upgrade 版本号` |
| 切回上次镜像 | `sh shike.sh rollback` |
| 停止，保留数据 | `sh shike.sh stop` |

账号、任务和记录存在 Docker 命名卷中。保留安装目录的 `.env`，不要随意改变文件夹名或 Compose 项目名，否则可能连接到另一个数据卷。不要执行 `docker compose down -v`，它会删除数据卷。

## 升级：一个命令，先备份再更换镜像

先查看目标 Release 的说明，再将下面的 `0.1.1` 换成实际已发布版本：

```bash
sh shike.sh upgrade 0.1.1
```

脚本会依次：

1. 下载目标镜像；下载失败时继续保留原服务。
2. 进入临时维护模式，禁止新的手动和定时执行；已有任务正在执行时退出维护，提示稍后重试。
3. 停止后端，将数据库、原加密密钥、首次设置凭证和 `.env` 备份到 `backups/时间戳/`。
4. 使用原数据卷启动新镜像，等待健康检查；成功后保存镜像选择并退出维护模式。
5. 若健康检查失败，尝试切回原镜像，**保留当前数据库**。若旧镜像也不兼容，则停止服务并显示备份位置，供人工恢复。

省略版本号时使用 `.env` 的 `SHIKE_IMAGE`；安装包默认固定版本，省略版本通常不会升级。希望跟随稳定版时，可将其改为 `ghcr.io/suversal/hdhive-auto-checkin:latest`，再运行 `sh shike.sh upgrade`。预发布版和 `edge` 不会覆盖 `latest`。

普通升级不清空账号、任务和记录，不需要重新扫码。服务短暂停止期间错过的计划按现有规则跳过，不集中补发。维护模式意外残留时，可执行 `docker compose exec shike python -m shike maintenance --disable`；维护标记也会在一小时后失效。

该命令更新应用镜像。如果某个 Release 要求更新 Compose 或管理脚本，下载新安装包，在原目录替换对应文件；保留原 `.env`、`.shike`、`backups` 和数据卷，再按该版本说明升级。

## 回退镜像和恢复数据有什么区别

升级后功能不合适，先尝试：

```bash
sh shike.sh rollback
```

这会再做一次备份，然后切回本机保存的上一次镜像，保留当前账号和执行记录。清理 Docker 镜像时不要删掉仍需使用的 `shike-rollback:*` 镜像。跨数据库格式的大版本升级是否允许回退，以对应 Release 说明为准。

只有数据损坏或明确需要旧数据时才恢复备份。恢复将覆盖现有账号、配置和记录；命令会先备份当前数据，再要求你输入 `RESTORE` 确认：

```bash
sh shike.sh restore backups/实际备份目录
```

恢复会校验归档、数据库和密钥，拒绝不完整、被修改的归档或不兼容的数据库格式。恢复后需要重新登录管理面板，**所有任务都暂停**；先核对 Telegram 实际会话和历史记录，再开启需要的任务，避免重复发送。

备份目录内 `data.tar.gz` 包含数据库和密钥，`config.env` 保存部署时的配置，`image.txt` 记录镜像。备份包含账号授权能力，文件权限默认只允许当前用户读取，请保存在自己的可信位置，不要上传公开仓库。

更换服务器时，先安装兼容版本的镜像，再停止实例，将备份放进新安装目录。必要时将原 `config.env` 复制为新 `.env` 并检查端口、域名和镜像设置；新空数据卷可通过以下命令恢复，再启动：

```bash
docker compose run --rm -T --no-deps shike python -m shike restore --archive - < backups/实际备份目录/data.tar.gz
sh shike.sh start
```

使用外部 `SHIKE_SECRET_KEY` 的实例，需要保留匹配的 `.env`；密钥不匹配时恢复会拒绝覆盖。

## 无脚本安装 / Windows Compose 用法

在安装目录复制示例文件为 `.env`，然后运行：

```bash
docker compose pull
docker compose up -d --wait
docker compose exec shike python -m shike setup-link
```

普通 Compose 命令不会自动添加备份步骤；升级和恢复推荐使用 WSL 中的 `shike.sh`。不要用 Watchtower 等工具自动替换这个有持久数据和调度器的服务，除非你另行保证了备份和执行互斥。

## 常见问题

- **`denied` / `unauthorized` / 镜像不存在**：核对版本；仓库维护者需要先发布镜像并将 GHCR 包设为 Public。Fork 用户发布到自己的命名空间后，使用对应安装包或修改 `SHIKE_IMAGE`。
- **`port is already allocated`**：在 `.env` 将 `SHIKE_PORT` 改为未占用端口，再启动。脚本会显示正确端口的入口。
- **健康检查失败**：运行 `sh shike.sh logs`。常见原因是数据卷权限或加密密钥不匹配，不要删除数据卷来尝试修复。
- **Telegram 超时**：服务器需要能连接 Telegram。在面板设置中配置服务器可用的代理；容器内的 `127.0.0.1` 不是宿主机代理。Docker Desktop 可使用 `host.docker.internal`，Linux 需要配置实际可达的宿主机或代理地址。
- **网页打不开**：服务器部署默认走 SSH 转发，或配置域名 HTTPS；不要直接把 `127.0.0.1` 当成服务器公网地址。
- **忘记管理密码**：停止服务，在同一数据卷执行 `docker compose run --rm --no-deps shike python -m shike reset-password`，按提示输入，再启动；Telegram 账号和任务保留。

## 开发者：源码构建和原有安装迁移

源码仓库保留构建覆盖文件，不依赖已发布镜像：

```bash
docker compose -f compose.yaml -f compose.build.yaml build
docker compose -f compose.yaml -f compose.build.yaml up -d --wait
docker compose exec shike python -m shike setup-link
```

镜像内部完成前端编译，运行层不包含 Node、测试、源码配置或开发依赖。原有使用 `docker compose up --build` 的开发安装，在同一文件夹、同一 `.env` 下按上述覆盖文件构建即可；卷名和 Compose 项目名保持不变。原镜像若没有维护命令，先在没有任务执行时停止服务、离线备份完整原数据卷，再构建新镜像。

源码构建完成后若使用管理脚本，在 `.env` 设置 `SHIKE_IMAGE=shike:local`，离线操作可显式使用 `SHIKE_PULL_POLICY=never sh shike.sh install`。公开用户优先使用 Release 安装包。
