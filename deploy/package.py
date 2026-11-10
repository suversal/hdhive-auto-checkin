"""Create the small Docker installation bundle attached to a Shike release."""
from __future__ import annotations

import argparse
import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_bundle(output: Path, version: str, repository: str):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("无效版本号")
    if not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", repository):
        raise ValueError("无效仓库名称")
    output.mkdir(parents=True, exist_ok=True)
    image = f"ghcr.io/{repository}:{version}"
    files = ["compose.yaml", "compose.https.yaml", ".env.shike.example", "shike.sh", "deploy/Caddyfile", "docs/docker-deployment.md"]
    archive_path = output / f"shike-docker-{version}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            content = (ROOT / name).read_text(encoding="utf-8")
            if name in ("compose.yaml", ".env.shike.example"):
                content = content.replace("ghcr.io/suversal/hdhive-auto-checkin:latest", image)
            info = zipfile.ZipInfo("shike/" + name)
            info.create_system = 3
            info.external_attr = (0o100755 if name.endswith(".sh") else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content.encode())
        archive.writestr("shike/README.txt", f"拾刻 {version}\n\n安装 Docker 后，在此目录运行：\n  sh shike.sh install\n\n详细步骤：docs/docker-deployment.md\n本安装包固定使用镜像 {image}\n升级：sh shike.sh upgrade 新版本号\n不要删除 .env、backups 或 Docker 数据卷。\n")
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (output / "SHA256SUMS").write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")
    return archive_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository", default="suversal/hdhive-auto-checkin")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(build_bundle(args.output, args.version, args.repository.lower()))
