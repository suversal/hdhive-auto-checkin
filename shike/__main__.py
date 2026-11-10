from __future__ import annotations

import argparse
import getpass
import json
import sqlite3
import tarfile
import sys

from .config import Config
from .database import Database
from .security import InstanceLock, Vault, password_hash


def main():
    parser = argparse.ArgumentParser(description="拾刻 Telegram 自动任务服务")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "open", "url", "init-admin", "reset-password", "maintenance", "backup", "restore"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--open", action="store_true", help="启动后自动打开登录页")
    parser.add_argument("--output", default="-", help="备份输出路径，默认输出到标准输出")
    parser.add_argument("--archive", help="要恢复的备份路径，- 表示标准输入")
    parser.add_argument("--replace", action="store_true", help="恢复时覆盖现有数据；恢复后的任务全部暂停")
    parser.add_argument("--password-stdin", action="store_true", help="从标准输入读取一行管理密码，仅供可信自动化；不要放在命令参数中")
    parser.add_argument("--workspace", default="我的工作空间", help="首次创建管理员时的工作空间名称")
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
            error = sys.exc_info()[1]
            parser.exit(1, f"维护未完成：{error}\n")
        return
    if args.command in ("open", "url"):
        link = config.public_url or f"http://127.0.0.1:{args.port}"
        if args.command == "url":
            print(link)
        else:
            import webbrowser
            webbrowser.open(link)
            print("已打开拾刻登录页。")
        return
    if args.command in ("init-admin", "reset-password"):
        lock = None
        try:
            Vault(config.data_dir)
            lock = InstanceLock(config.data_dir)
            db = Database(config.data_dir)
            initialized = bool(db.get("admin_password"))
            if args.command == "init-admin" and initialized:
                print("管理员已设置，保留现有密码。需要重设时请使用 reset-password。")
                return
            if args.command == "reset-password" and not initialized:
                raise ValueError("管理员尚未设置，请使用 init-admin。")
            if args.password_stdin:
                password = sys.stdin.readline(4098).removesuffix("\n").removesuffix("\r")
            else:
                if not sys.stdin.isatty():
                    raise ValueError("请在交互终端运行以隐藏密码输入；自动化请显式使用 --password-stdin。")
                password = getpass.getpass("管理密码（至少 10 位，输入不回显）: ")
                confirmation = getpass.getpass("再次输入: ")
                if password != confirmation:
                    raise ValueError("两次输入的密码不一致。")
            if not 10 <= len(password) <= 1024:
                raise ValueError("管理密码需要 10 到 1024 位。")
            if args.command == "init-admin":
                from .admin import initialize_admin
                initialize_admin(db, password, args.workspace)
                print("管理员已创建。请打开面板，使用刚设置的管理密码登录。")
            else:
                with db.tx(True) as connection:
                    db.set("admin_password", password_hash(password), connection=connection)
                    connection.execute("DELETE FROM sessions")
                print("管理密码已更新，旧登录已失效。")
        except (EOFError, KeyboardInterrupt):
            parser.exit(1, "已取消密码设置。\n")
        except (ValueError, RuntimeError, OSError, sqlite3.Error) as error:
            parser.exit(1, f"密码设置未完成：{error}\n")
        finally:
            if lock:
                lock.close()
        return
    import uvicorn
    from .app import create_app
    # No reload/workers: exactly one process owns the durable scheduler and clients.
    uvicorn.run(create_app(config), host=args.host, port=args.port, access_log=False, log_level="info")


if __name__ == "__main__":
    main()
