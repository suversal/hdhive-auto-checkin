# 拾刻安装、升级与恢复

拾刻提供两种独立用法：不需要网页管理时，使用仓库原有的 GitHub Actions 入门脚本；需要网页配置、扫码接入和执行记录时，使用这里的 Docker 完整版。

## 先准备什么

- 一台能连接 Telegram 的常开电脑、NAS 或 Linux 服务器。
- Docker 和 `docker compose` 插件。Windows / macOS 用户可安装 [Docker Desktop](https://docs.docker.com/get-started/get-docker/)，服务器按 [Docker Engine 官方指南](https://docs.docker.com/engine/install/) 安装。
- 支持 Linux AMD64 和 ARM64。Windows 使用 Linux 容器；脚本命令可在 WSL 终端运行。32 位 ARM 不在镜像支持范围内。

安装过程中不需要在宿主机安装 Python、Node。当前源码构建方式还需要 Git，并创建一份 `.env`；管理密码在终端按提示设置。

## 方式一：当前使用源码构建

目前尚未发布正式 Release 安装包。首次部署先使用下面的源码构建方式，不要直接尝试拉取 `latest`。在要部署的机器上运行；已有安装目录时请跳到[源码升级](#源码构建版升级)，不要覆盖原配置：

```bash
git clone --depth 1 --branch codex/shike-backend https://github.com/suversal/hdhive-auto-checkin.git shike
cd shike
sed 's|^SHIKE_IMAGE=.*|SHIKE_IMAGE=shike:local|' .env.shike.example > .env
docker compose -f compose.yaml -f compose.build.yaml build
SHIKE_PULL_POLICY=never sh shike.sh install
```

先创建 `.env`，再构建，可确保 Compose 和管理脚本都使用同一个 `shike:local` 镜像。`SHIKE_PULL_POLICY=never` 让安装跳过远端拉取。

按提示设置并确认管理密码（至少 10 位，输入不回显），健康检查通过后继续下方的本机 / SSH 访问说明。服务运行后在网页填写 Telegram API 信息，详见 [API ID / API Hash 申请](https://github.com/suversal/hdhive-auto-checkin/blob/codex/shike-backend/docs/telegram-api.md)。

Linux 若需要 `sudo` 操作 Docker，构建命令加 `sudo`，安装命令使用 `sudo env SHIKE_PULL_POLICY=never sh shike.sh install`；后续管理命令也需相应权限。

## 方式二：已有正式 Release 安装包时

以下方式需要维护者已经成功发布镜像和附件。去项目的 [Releases](https://github.com/suversal/hdhive-auto-checkin/releases) 核对，找不到对应文件时使用上方源码构建，不要猜版本号。

1. 下载对应 Release 的 `shike-docker-版本号.zip`，解压得到 `shike` 文件夹。不要下载 GitHub 自动生成的 Source code 代替安装包。
2. 启动 Docker，在解压文件夹中打开终端，运行：

   ```bash
   sh shike.sh install
   ```

3. 按终端提示设置并确认管理密码（至少 10 位，输入不回显）。等待健康检查通过，打开显示的网页入口，用这个密码登录。
4. 根据页面引导填写 Telegram API ID / API Hash（[申请步骤](https://github.com/suversal/hdhive-auto-checkin/blob/codex/shike-backend/docs/telegram-api.md)），然后扫码接入账号，创建第一条任务。

安装包固定使用对应版本的镜像，不会自动跳到其他版本。默认入口是 `http://127.0.0.1:8787`，只允许本机访问。网页只提供管理密码登录，不开放公开注册；更换设备无需重新初始化。安装中断或已有未初始化的实例，可运行 `sh shike.sh init` 补设密码并启动。

发布流水线不会因为下载源码就自动执行。正式安装包依赖镜像已经发布且公开，安装前不需要登录维护者的 GHCR 账号。

## 本机访问

在部署机器的浏览器打开 `http://127.0.0.1:8787`，使用终端设置的管理密码登录。首次设置未完成时运行 `sh shike.sh init`；忘记密码用 `sh shike.sh reset-password`。

## 装在云服务器：先通过 SSH 打开

服务器上安装完成后，在**你自己的电脑**终端运行，将 `用户名` 和 `服务器地址` 换成实际值：

```bash
ssh -N -L 8787:127.0.0.1:8787 用户名@服务器地址
```

保持该终端开启，然后在自己电脑的浏览器打开安装命令显示的入口。浏览器里的 `127.0.0.1` 指自己的电脑，SSH 会把访问转发到服务器。

若本机 8787 已被占用，可把转发命令第一个端口改为 8789，同时把浏览器入口中的端口改成 8789。

## 有域名：可选自动 HTTPS

1. 将域名的 DNS 记录指向服务器，放行服务器的 TCP 80、443 端口，确认没有其他服务占用它们。
2. 在上方完成安装后，编辑原目录的 `.env`，**不要用示例覆盖现有配置**。
3. 填写这一项，镜像等其他内容保持原样：

   ```dotenv
   SHIKE_DOMAIN=shike.example.com
   ```

4. 挑没有任务执行的时候运行下面的命令。先下载 Caddy，再启动已有实例（`start` 本身不拉取缺失的镜像）：

   ```bash
   docker compose -f compose.yaml -f compose.https.yaml pull caddy
   sh shike.sh start
   ```

脚本自动加载 `compose.https.yaml`，由 Caddy 申请证书并转发到后端。之后使用 `https://你的域名`，账号和任务继续保留。

证书申请需要域名能从公网解析并访问服务器。Caddy 的证书保存在独立 Docker 卷中，普通升级会保留。

已有 HTTPS 反向代理时，留空 `SHIKE_DOMAIN`，填写 `SHIKE_PUBLIC_URL=https://你的域名`，让现有代理转发到本机 8787 并保留 Host，再运行 `sh shike.sh start` 应用配置。若代理也在容器中，使用它能访问的后端地址，代理容器自己的 `127.0.0.1` 并不是宿主机。不要将管理面板直接开放为公网明文 HTTP。暂不支持 `/shike` 等域名子路径。

## 常用命令

在安装文件夹中运行：

| 操作 | 命令 |
| --- | --- |
| 启动或恢复服务 | `sh shike.sh start` |
| 找回登录入口 | `sh shike.sh open` |
| 首次补设管理密码 | `sh shike.sh init` |
| 重设管理密码 | `sh shike.sh reset-password` |
| 查看健康与运行状态 | `sh shike.sh status` |
| 查看日志，按 Ctrl+C 退出 | `sh shike.sh logs` |
| 备份 | `sh shike.sh backup` |
| 升级到指定已发布版本 | `sh shike.sh upgrade 版本号` |
| 切回上次镜像 | `sh shike.sh rollback` |
| 停止，保留数据 | `sh shike.sh stop` |

账号、任务和记录存在 Docker 命名卷中。保留安装目录的 `.env`，不要随意改变文件夹名或 Compose 项目名，否则可能连接到另一个数据卷。不要执行 `docker compose down -v`，它会删除数据卷。

## 源码构建版升级

在原安装目录保留现有 `.env` 和卷，镜像仍使用 `SHIKE_IMAGE=shike:local`：

```bash
git pull --ff-only
docker compose -f compose.yaml -f compose.build.yaml build
SHIKE_PULL_POLICY=never sh shike.sh upgrade
```

构建完成后，由管理脚本备份并替换容器。不要直接用 `docker compose up --build` 绕过维护和备份；无需加版本号，否则会把本地镜像名改成不存在的版本标签。回退后脚本可能把 `.env` 指向 `shike-rollback:*`；下次源码升级前先把 `SHIKE_IMAGE` 改回 `shike:local`，其他配置保持原样。

## 正式镜像升级：先备份再更换镜像

先查看目标 Release 的说明，再将下面的 `0.1.1` 换成实际已发布版本：

```bash
sh shike.sh upgrade 0.1.1
```

脚本会依次：

1. 下载目标镜像；下载失败时继续保留原服务。
2. 进入临时维护模式，禁止新的手动和定时执行；已有任务正在执行时退出维护，提示稍后重试。
3. 停止后端，将数据库、原加密密钥和 `.env` 备份到 `backups/时间戳/`。
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

## 无脚本安装 / Windows Compose 用法（已发布镜像）

此方式依赖公开镜像。尚未发布时按本文开头构建；Windows 新用户推荐在 WSL 使用管理脚本。

在安装目录复制示例文件为 `.env`，然后运行：

```bash
docker compose pull
docker compose run --rm --no-deps shike python -m shike init-admin
docker compose up -d --wait
```

普通 Compose 命令不会自动添加备份步骤；升级和恢复推荐使用 WSL 中的 `shike.sh`。不要用 Watchtower 等工具自动替换这个有持久数据和调度器的服务，除非你另行保证了备份和执行互斥。

## 常见问题

- **`denied` / `unauthorized` / 镜像不存在**：核对版本；仓库维护者需要先发布镜像并将 GHCR 包设为 Public。Fork 用户发布到自己的命名空间后，使用对应安装包或修改 `SHIKE_IMAGE`。
- **`port is already allocated`**：在 `.env` 将 `SHIKE_PORT` 改为未占用端口，再启动。脚本会显示正确端口的入口。
- **健康检查失败**：运行 `sh shike.sh logs`。常见原因是数据卷权限或加密密钥不匹配，不要删除数据卷来尝试修复。
- **Telegram 超时**：服务器需要能连接 Telegram。在面板设置中配置服务器可用的代理；容器内的 `127.0.0.1` 不是宿主机代理。Docker Desktop 可使用 `host.docker.internal`，Linux 需要配置实际可达的宿主机或代理地址。
- **网页打不开**：服务器部署默认走 SSH 转发，或配置域名 HTTPS；不要直接把 `127.0.0.1` 当成服务器公网地址。
- **忘记管理密码**：运行 `sh shike.sh reset-password`，脚本确认没有活动执行后暂停服务，按终端提示输入密码，再恢复服务；Telegram 账号和任务保留。
- **页面提示尚未设置管理密码**：在安装目录运行 `sh shike.sh init`，完成后刷新登录页。初始化只能在部署端进行，已有管理员不会被该命令覆盖。

## 开发者：原有源码安装迁移

源码仓库保留构建覆盖文件，不依赖已发布镜像。已有 `.env` 时不要重新生成；先确认其中 `SHIKE_IMAGE=shike:local`，再运行：

```bash
docker compose -f compose.yaml -f compose.build.yaml build
SHIKE_PULL_POLICY=never sh shike.sh install
```

以上 `install` 只用于尚未创建容器的新实例；检测到已有实例时会提示使用 `upgrade`。正常源码升级用上方“源码构建版升级”。原镜像若没有维护命令，先在没有任务执行时停止服务、离线备份完整原数据卷，再在原 Compose 项目下构建和启动；不要在未停止的旧服务旁运行一次性初始化容器。

镜像内部完成前端编译，运行层不包含 Node、测试、源码配置或开发依赖。卷名和 Compose 项目名保持不变。直接运行 Python 源码的开发说明见[本地开发](https://github.com/suversal/hdhive-auto-checkin/blob/codex/shike-backend/docs/development.md)。
