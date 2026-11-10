"""Docker deployment smoke test; synthetic state only, no Telegram connection."""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_test(image: str):
    suffix = uuid.uuid4().hex[:10]
    project = "shike-smoke-" + suffix
    environment = {k: v for k, v in os.environ.items() if not k.startswith(("SHIKE_", "COMPOSE_"))}
    environment.update(COMPOSE_PROJECT_NAME=project, SHIKE_PULL_POLICY="never")
    tags = []
    with tempfile.TemporaryDirectory(prefix=project + "-") as temporary:
        directory = Path(temporary)
        for name in ("compose.yaml", "compose.https.yaml", ".env.shike.example", "shike.sh", "deploy/Caddyfile"):
            target = directory / name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        (directory / ".env").write_text(f"SHIKE_IMAGE={image}\nSHIKE_PORT={port}\nSHIKE_BIND_ADDRESS=127.0.0.1\nSHIKE_DOMAIN=\nSHIKE_PUBLIC_URL=\nSHIKE_SECRET_KEY=\nSHIKE_SETUP_TOKEN=\n")
        os.chmod(directory / ".env", 0o600)

        def command(*args, input=None, check=True):
            result = subprocess.run(args, cwd=directory, env=environment, input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if check and result.returncode:
                raise RuntimeError(f"Deployment smoke command failed: {args[0:2]}\n{result.stderr.decode(errors='replace')[-2000:]}")
            return result

        def compose(*args, **kwargs):
            return command("docker", "compose", "-f", str(directory / "compose.yaml"), *args, **kwargs)

        def script(*args, **kwargs):
            return command("sh", "shike.sh", *args, **kwargs)

        cookies = http.cookiejar.CookieJar()
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
        base = f"http://127.0.0.1:{port}"

        def request(path, body=None):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json", "Origin": base})
            with client.open(req, timeout=10) as response:
                content = response.read()
                return json.loads(content) if "application/json" in response.headers.get("Content-Type", "") else content

        def assert_workspace():
            assert request("/api/state")["settings"]["workspace"] == "Docker 合成验收"

        try:
            script("install")  # Output deliberately captured: bootstrap URL stays private.
            assert request("/api/health")["status"] == "ok"
            for resource in ("/", "/assets/app.js", "/assets/styles.css", "/assets/calendar.css", "/assets/THIRD_PARTY_NOTICES.txt"):
                assert request(resource)
            token = compose("exec", "-T", "shike", "python", "-m", "shike", "setup-token").stdout.decode().strip()
            request("/api/auth/setup", {"setupToken": token, "password": "synthetic-docker-password", "workspace": "Docker 合成验收"})
            assert_workspace()
            print("PASS: install, health, assets and initial management setup", flush=True)
            compose("exec", "-T", "shike", "python", "-c", "from pathlib import Path; import os; assert os.getuid()!=0; assert not Path('/app/web/node_modules').exists(); assert not Path('/app/server/tests').exists(); assert not Path('/app/local.config.json').exists(); assert not list(Path('/app/web').glob('*.jsx'))")
            compose("restart", "shike")
            for _ in range(40):
                try:
                    assert_workspace()
                    break
                except Exception:
                    time.sleep(.25)
            else:
                raise AssertionError("Restart persistence failed")
            script("backup")
            archive_dir = next((directory / "backups").iterdir())
            assert (archive_dir / "data.tar.gz").stat().st_size > 0
            assert_workspace()
            print("PASS: restart persistence and offline backup", flush=True)

            # Produce different local image configurations without external side effects.
            repository = project
            for version, broken in (("9.9.1", False), ("9.9.2", True)):
                tag = f"{repository}:{version}"
                dockerfile = f"FROM {image}\nLABEL shike.smoke={version}\n"
                if broken:
                    dockerfile += 'HEALTHCHECK --interval=1s --timeout=1s --start-period=1s --retries=1 CMD ["python", "-c", "raise SystemExit(1)"]\n'
                command("docker", "build", "--network=none", "-t", tag, "-", input=dockerfile.encode())
                tags.append(tag)
            # An alias with the same ID represents the pre-upgrade image.
            initial = f"{repository}:base"
            command("docker", "tag", image, initial)
            tags.append(initial)
            env_path = directory / ".env"
            env_path.write_text(env_path.read_text().replace(f"SHIKE_IMAGE={image}", f"SHIKE_IMAGE={initial}"))
            script("upgrade", "9.9.1")
            assert_workspace()
            print("PASS: upgrade with original data volume", flush=True)
            assert f"SHIKE_IMAGE={repository}:9.9.1" in env_path.read_text()
            failed = script("upgrade", "9.9.2", check=False)
            if failed.returncode == 0:
                print(failed.stdout.decode(errors="replace"), flush=True)
                print(failed.stderr.decode(errors="replace")[-2000:], flush=True)
            assert failed.returncode != 0, "Broken health check should roll back"
            assert_workspace()
            assert "SHIKE_IMAGE=shike-rollback:" in env_path.read_text()
            script("rollback")
            assert_workspace()
            script("upgrade", "9.9.1")
            assert_workspace()
            assert f"SHIKE_IMAGE={repository}:9.9.1" in env_path.read_text(), "Rollback must preserve the upstream image repository"

            environment["SHIKE_CONFIRM_RESTORE"] = "yes"
            script("restore", str(archive_dir))
            cookies.clear()
            request("/api/auth/login", {"password": "synthetic-docker-password"})
            assert_workspace()
            assert compose("exec", "-T", "shike", "python", "-m", "shike", "maintenance").stdout.decode().find('"maintenance": false') >= 0
            print("PASS: Docker install, assets, non-root, persistence, backup, upgrade, failed-health fallback, rollback, restore; no Telegram messages")
        finally:
            # Only this uniquely named project and its volumes are removed.
            compose("down", "-v", "--remove-orphans", check=False)
            rollback_tags = command("docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}", "--filter", f"reference=shike-rollback:{project}-*", check=False).stdout.decode().splitlines()
            if tags:
                command("docker", "image", "rm", *tags, check=False)
            if rollback_tags:
                command("docker", "image", "rm", *rollback_tags, check=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    run_test(parser.parse_args().image)
