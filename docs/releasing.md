# 拾刻镜像发布

原 GitHub Actions 入门方案保持独立；`.github/workflows/checkin.yml` 不参与镜像发布，也不随发布任务执行真实签到。

## 当前对外入口

默认分支 `codex/shike-backend` 的根目录 `README.md` 是 Web 面板介绍和部署入口；`README.actions.md` 与 `telethon` 分支保存独立脚本入门方案。`README.shike.md` 只保留旧链接导航。发布时一并检查这些入口，避免仓库首页又显示成脚本教程。

目前尚无正式 Release 安装包，首页和部署指南默认推荐源码构建。首次完成下面的发布流程，并在未登录 GHCR 的环境验证安装包可用后，再把首页和部署指南的首选安装方式切换为正式安装包；在那之前不要写“下载即可安装”。

## 首次发布

1. 将完整后端、前端、部署文件和两个 `shike-*.yml` 工作流提交到要发布的版本，推送到 GitHub。确认仓库允许 GitHub Actions，工作流权限允许其声明的 `packages: write` 和 Release 附件写入。
2. 更新 `shike/__init__.py` 的 `__version__`，例如 `0.1.0`。
3. 创建 GitHub Release，标签命名为 `shike-v0.1.0`，目标选择包含本轮实现的提交；先写好变更和升级说明，再点击 Publish release。
4. `Publish Shike Docker` 自动先运行后端、旧方案单元测试、前端构建一致性和 Docker 冒烟检查；全部通过后，构建并发布 AMD64 / ARM64 镜像。
5. 首次到仓库关联的 Packages → 对应包 → Package settings，将可见性改成 **Public**。GHCR 新包可能默认私有，公共源码仓库不会保证包自动公开。
6. 检查 Release 下出现 `shike-docker-0.1.0.zip` 与 `SHA256SUMS`，并在未登录 GHCR 的环境确认可拉取，再对外推荐安装。

镜像名称自动使用小写的 `ghcr.io/仓库所有者/仓库名`。本仓库为 `ghcr.io/suversal/hdhive-auto-checkin`；Fork 发布不写入原作者命名空间，不需要个人访问令牌，使用 GitHub 自动提供的 `GITHUB_TOKEN`。

## 版本与触发规则

| 触发方式 | 发布标签 |
| --- | --- |
| 正式 Release `shike-v0.1.0` | `0.1.0`、`latest`、完整提交 SHA 标签 |
| 预发布 Release，例如 `shike-v0.2.0-rc.1` | 对应完整版本、提交 SHA；不更新 `latest` |
| 手动运行工作流 | `edge`、提交 SHA；不更新 `latest`，不生成正式安装包 |
| Pull request / 普通分支提交 | 只检查，不发布镜像 |

Release 标签必须与代码版本完全一致。正式发布从当前稳定线向前推进；不要把旧维护版本作为新的稳定 Release 发布并覆盖 `latest`。预发布版请勾选 GitHub 的 pre-release 标记。现有入门版的其他标签不会触发拾刻发布。

正式安装包固定镜像版本，包含 Compose、示例配置、管理脚本、HTTPS 配置及安装指南，不包含真实账号、配置、密钥、数据库或 Node 开发依赖。镜像带源码地址、版本和提交标签，并生成构建来源信息和 SBOM。

## 发布前检查

先检查面向用户的说明：

- Web 首页提供当前可用的安装命令、API 申请、账号授权与任务入口；图片只含演示数据，所有链接可在 GitHub 打开。
- `telethon` 文档说明 Fork 的默认分支、工作流启用和 Secrets 迁移；历史分支明确自身用途，不混用三套账号配置。
- Release 版本、标签、镜像和附件名称一致；确认本版本升级和回退条件。README 中的示例版本不代表该版本已经发布。
- 仓库公开不等于已经声明开源许可。正式推广前由维护者选择许可协议并提供对应 LICENSE，再在首页明确说明。

发布应用版本时再运行以下完整检查；仅修改说明文件时核对链接、示例和打包文档即可：

```bash
python -m pytest server/tests -q
TELEGRAM_LOCAL_CONFIG_PATH=/tmp/shike-no-local-config.json python -m unittest discover -s tests
npm ci --prefix web
npm run build --prefix web
docker build -f Dockerfile.shike -t shike:release-check .
python deploy/smoke.py --image shike:release-check
python deploy/package.py --version 0.1.0
```

冒烟测试创建独立的临时容器和卷，只使用合成管理配置，不连接 Telegram，也不读取本机 `var/shike`。覆盖安装、健康和资源、持久化、备份恢复、升级与镜像回退，最后清理测试容器和卷。

Release 说明至少写清楚新增和修复、数据库格式是否变化、能否回退旧镜像、是否需要用户手动操作。本轮数据库格式仍为 1。

自动发布流水线在本地编写和验证完成，不代表远端镜像已经存在。只有 GitHub 上成功执行发布工作流并完成包可见性设置后，公开安装路径才算验收完成。

参考：[GitHub 发布容器镜像](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)、[GHCR 包权限与可见性](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)、[Docker Compose 健康等待](https://docs.docker.com/reference/cli/docker/compose/up/)。
