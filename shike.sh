#!/bin/sh
# Docker-only user entry point. No host Python/Node and no sourced .env code.
set -eu
umask 077
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
command_name=${1:-help}
shift "$(( $# > 0 ? 1 : 0 ))"

die() { printf '%s\n' "$*" >&2; exit 1; }
help() {
    cat <<'HELP'
拾刻 Docker 管理
  sh shike.sh install           拉取镜像、启动并显示首次设置入口
  sh shike.sh start             启动已安装实例
  sh shike.sh open              显示设置或登录入口
  sh shike.sh status            查看运行与健康状态
  sh shike.sh logs              查看最近日志（Ctrl+C 退出）
  sh shike.sh backup            暂停调度，备份后恢复服务
  sh shike.sh upgrade [0.1.1]   备份并升级，省略版本时使用 .env 配置
  sh shike.sh rollback          切回上次升级前的本地镜像，保留当前数据
  sh shike.sh restore 备份目录  覆盖恢复数据；恢复后所有任务暂停
  sh shike.sh stop              停止服务，保留数据

首次安装自动创建 .env。填写 SHIKE_DOMAIN 可启用自带 HTTPS。
开发/离线镜像可设置 SHIKE_PULL_POLICY=never，跳过拉取。
HELP
}
case "$command_name" in
    help|-h|--help) help; exit 0 ;;
    install|start|open|status|logs|backup|upgrade|rollback|restore|stop) ;;
    *) help; die "未知命令：$command_name" ;;
esac
command -v docker >/dev/null 2>&1 || die "请先安装并启动 Docker Desktop，或在服务器安装 Docker Engine 与 Compose 插件。"
docker compose version >/dev/null 2>&1 || die "请安装 Docker Compose 插件（使用 docker compose，不是 docker-compose）。"
docker info >/dev/null 2>&1 || die "Docker 尚未启动，或当前用户没有 Docker 使用权限。"
if [ ! -f .env ]; then
    cp .env.shike.example .env
    chmod 600 .env
    printf '%s\n' "已创建 .env；默认只允许本机访问。"
fi
# Only this simple flag selects the optional file. Docker parses all values itself.
https=0
domain=$(sed -n 's/^[[:space:]]*SHIKE_DOMAIN[[:space:]]*=[[:space:]]*//p' .env | tail -n 1 | tr -d "\"'" | sed 's/[[:space:]]*#.*$//;s/[[:space:]]*$//')
if [ -n "$domain" ]; then
    printf '%s' "$domain" | grep -Eq '^[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}$' || die "SHIKE_DOMAIN 请填写完整域名，不要带 https://、端口或路径。"
    https=1
fi
compose() {
    if [ "$https" = 1 ]; then
        docker compose --project-directory "$ROOT" --env-file "$ROOT/.env" -f "$ROOT/compose.yaml" -f "$ROOT/compose.https.yaml" "$@"
    else
        docker compose --project-directory "$ROOT" --env-file "$ROOT/.env" -f "$ROOT/compose.yaml" "$@"
    fi
}
up() { compose up -d --pull never --wait --wait-timeout 120; }
pull() {
    if [ "${SHIKE_PULL_POLICY:-always}" = never ]; then
        docker image inspect "$1" >/dev/null || die "本机没有指定镜像：$1"
    else
        docker pull "$1" || die "镜像拉取失败，原服务和数据未改动。首次发布前请使用源码构建方案；也请检查版本、网络和 GHCR 包是否公开。"
    fi
}
entry() {
    binding=$(compose port shike 8787)
    port=${binding##*:}
    printf '\n%s\n' "请在自己的浏览器打开下面的入口："
    compose exec -T shike python -m shike setup-link --port "$port"
    if [ "$https" = 0 ]; then
        printf '%s\n' "云服务器用户：先按部署指南建立 SSH 端口转发，再在自己电脑浏览器打开入口。"
    fi
}
case "$command_name" in
    status) compose ps; exit ;;
    logs) compose logs --tail 100 -f; exit ;;
    open) entry; exit ;;
esac
mkdir -p .shike backups
chmod 700 .shike backups
mkdir .shike/operation.lock 2>/dev/null || die "另一个安装或维护命令正在运行。若上次被强制终止，请先确认没有维护进程，再删除 .shike/operation.lock。"
gated=0
restart_needed=0
cleanup() {
    result=$?
    trap - EXIT HUP INT TERM
    if [ "$restart_needed" = 1 ]; then
        up >&2 || printf '%s\n' "服务未能恢复，请运行 sh shike.sh status / logs 检查。" >&2
    fi
    if [ "$gated" = 1 ]; then
        compose exec -T shike python -m shike maintenance --disable >/dev/null 2>&1 || true
    fi
    rmdir .shike/operation.lock 2>/dev/null || true
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM
configured=$(compose config --images shike)
case "$command_name" in
    install)
        if [ -n "$(compose ps -a -q shike)" ]; then
            printf '%s\n' "检测到已有实例。启动请用 sh shike.sh start，更新请用 sh shike.sh upgrade；不会跳过备份直接覆盖。"
            exit
        fi
        pull "$configured"
        if [ "$https" = 1 ]; then compose pull caddy; fi
        up
        entry
        exit ;;
    start) up; entry; exit ;;
    stop) compose stop; printf '%s\n' "已停止，账号和任务数据保留。"; exit ;;
esac

current=$(compose ps -a -q shike)
[ -n "$current" ] || die "没有已安装的实例，请先运行 sh shike.sh install。"
old_id=$(docker inspect --format '{{.Image}}' "$current")
stamp=$(date -u +%Y%m%dT%H%M%SZ)-$$
project_name=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$current")
project_slug=$(printf '%.40s' "$project_name")
old_ref="shike-rollback:${project_slug}-${stamp}"
docker image tag "$old_id" "$old_ref"

# Freeze image selection before pulling a mutable tag such as latest.
case "$command_name" in
    upgrade)
        update_source=$configured
        case "$update_source" in
            shike-rollback:*)
                [ -f .shike/update-source ] || die "请先在 .env 中将 SHIKE_IMAGE 改成原来的仓库镜像，再选择升级版本。"
                update_source=$(cat .shike/update-source) ;;
        esac
        target=$update_source
        if [ "$#" -gt 0 ]; then
            printf '%s' "$1" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$' || die "版本应为 0.1.1 或 0.2.0-rc.1。"
            repository=${update_source%@*}
            case "${repository##*/}" in *:*) repository=${repository%:*} ;; esac
            target="$repository:$1"
        fi
        pull "$target"
        target_id=$(docker image inspect --format '{{.Id}}' "$target")
        if [ "$target_id" = "$old_id" ]; then
            printf '%s\n' "已经是指定镜像，无需升级。"
            exit
        fi
        if [ ! -f .shike/update-source ]; then
            printf '%s\n' "$update_source" > .shike/update-source
        fi ;;
    rollback)
        [ -f .shike/previous-image ] || die "没有上次升级前的镜像记录。"
        target=$(cat .shike/previous-image)
        docker image inspect "$target" >/dev/null || die "上次镜像已被清理，请按备份中的版本说明恢复。" ;;
    restore)
        [ "$#" -eq 1 ] || die "用法：sh shike.sh restore backups/备份目录"
        archive_dir=$(CDPATH='' cd -- "$1" && pwd)
        [ -f "$archive_dir/data.tar.gz" ] || die "该目录缺少 data.tar.gz。"
        [ -t 0 ] || [ "${SHIKE_CONFIRM_RESTORE:-}" = yes ] || die "恢复会覆盖当前数据。请在终端交互确认后执行。"
        if [ "${SHIKE_CONFIRM_RESTORE:-}" != yes ]; then
            printf '%s' "恢复会覆盖当前账号、配置和记录，恢复后所有任务暂停。输入 RESTORE 继续："
            read -r answer
            [ "$answer" = RESTORE ] || die "已取消恢复。"
        fi ;;
esac
export SHIKE_IMAGE="$old_ref"
state=$(compose exec -T shike python -m shike maintenance --enable) || die "无法进入维护模式。旧开发镜像请先按源码迁移说明更新。"
gated=1
printf '%s' "$state" | grep -Eq '"activeRuns":[[:space:]]*0([,}])' || die "还有任务正在执行，未停止服务。请等任务结束后再试。"
compose stop shike
restart_needed=1
backup_dir="$ROOT/backups/$stamp"
mkdir "$backup_dir"
cp .env "$backup_dir/config.env"
docker image inspect --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}' "$old_id" > "$backup_dir/image.txt"
if compose run --rm -T --no-deps shike python -m shike backup > "$backup_dir/data.tar.gz.part"; then
    mv "$backup_dir/data.tar.gz.part" "$backup_dir/data.tar.gz"
else
    rm -f "$backup_dir/data.tar.gz.part"
    die "备份失败，已取消操作；将恢复原服务。"
fi
printf '%s\n' "已完整备份数据库、密钥和部署配置：$backup_dir"
if [ "$command_name" = backup ]; then
    up
    restart_needed=0
    printf '%s\n' "备份完成，服务已恢复。备份含账号授权，请妥善保管。"
    exit
fi
set_image() {
    awk -v image="$1" '!/^[[:space:]]*SHIKE_IMAGE[[:space:]]*=/ {print} END {print "SHIKE_IMAGE=" image}' .env > .shike/env.next
    mv .shike/env.next .env
}
if [ "$command_name" = restore ]; then
    # Existing data was backed up above. Restore uses the current deployment config.
    compose run --rm -T --no-deps shike python -m shike restore --archive - --replace < "$archive_dir/data.tar.gz"
    up
    restart_needed=0
    printf '%s\n' "恢复完成，所有任务已暂停。请登录核对，再开启所需任务。"
    exit
fi
export SHIKE_IMAGE="$target"
restart_needed=0
if up; then
    set_image "$target"
    if [ "$command_name" = upgrade ]; then
        printf '%s\n' "$target" > .shike/update-source
    fi
    printf '%s\n' "$old_ref" > .shike/previous-image
    printf '%s\n' "更新完成，健康检查通过。账号、任务、记录保留。"
else
    printf '%s\n' "新镜像健康检查未通过，正在切回原镜像；不会自动恢复旧数据库。" >&2
    compose stop shike
    export SHIKE_IMAGE="$old_ref"
    set_image "$old_ref"
    if up; then
        die "更新未完成，原镜像已恢复。备份位于 ${backup_dir}。"
    else
        compose stop shike
        die "原镜像也无法读取当前数据，服务已停止。请按部署指南选择兼容镜像或手动恢复备份。"
    fi
fi
