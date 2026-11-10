from __future__ import annotations

import argparse
import getpass
import secrets
import json
import sqlite3
import tarfile

from .config import Config
from .database import Database
from .security import InstanceLock, Vault, password_hash, setup_link


def main():
    parser = argparse.ArgumentParser(description="拾刻 Telegram 自动任务服务")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "open", "setup-link", "setup-token", "reset-password", "maintenance", "backup", "restore"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器，首次设置无需复制口令")
    parser.add_argument("--output", default="-", help="备份输出路径，默认输出到标准输出")
    parser.add_argument("--archive", help="要恢复的备份路径，- 表示标准输入")
    parser.add_argument("--replace", action="store_true", help="恢复时覆盖现有数据；恢复后的任务全部暂停")
    switches = parser.add_mutually_exclusive_group()
    switches.add_argument("--enable", action="store_true", help="启用临时维护模式")
    switches.add_argument("--disable", action="store_true", help="结束临时维护模式")
    args = parser.parse_args()
    config = Config.from_env()
    config.local_port, config.open_browser = args.port, args.open
    if args.command in ("maintenance", "backup", "restore"):
        from .maintenance import backup, maintenance, restore
        try:
            if args.command == "maintenance":
                print(json.dumps(maintenance(config.data_dir, True if args.enable else False if args.disable else None)))
            elif args.command == "backup":
                backup(config.data_dir, args.output)
            else:
                if not args.archive:
                    parser.error("restore 需要 --archive 备份路径。")
                restore(config.data_dir, args.archive, args.replace)
                print("数据恢复完成。所有任务已暂停，请登录面板核对后按需开启。")
        except (ValueError, RuntimeError, OSError, sqlite3.Error, tarfile.TarError):
            import sys
            error = sys.exc_info()[1]
            parser.exit(1, f"维护未完成：{error}\n")
        return
    if args.command in ("open", "setup-link"):
        vault = Vault(config.data_dir)
        db = Database(config.data_dir)
        base = config.public_url or f"http://127.0.0.1:{args.port}"
        link = base if db.get("admin_password") else setup_link(base, vault.setup_token)
        if args.command == "setup-link":
            print(link)
        else:
            import webbrowser
            webbrowser.open(link)
            print("已打开拾刻入口，请在浏览器完成设置或登录。")
        return
    if args.command == "setup-token":
        print(Vault(config.data_dir).setup_token)
        return
    if args.command == "reset-password":
        vault = Vault(config.data_dir)
        lock = InstanceLock(config.data_dir)
        try:
            db = Database(config.data_dir)
            if not db.get("admin_password"):
                parser.error("实例尚未初始化，请使用网页首次设置。")
            password = getpass.getpass("新的管理密码（至少 10 位）: ")
            confirmation = getpass.getpass("再次输入: ")
            if len(password) < 10 or password != confirmation:
                parser.error("密码不足 10 位或两次输入不一致。")
            with db.tx(True) as connection:
                db.set("admin_password", password_hash(password), connection=connection)
                connection.execute("DELETE FROM sessions")
            print("管理密码已更新，旧登录已失效。")
        finally:
            lock.close()
        return
    import uvicorn
    from .app import create_app
    # No reload/workers: exactly one process owns the durable scheduler and clients.
    uvicorn.run(create_app(config), host=args.host, port=args.port, access_log=False, log_level="info")


if __name__ == "__main__":
    main()
