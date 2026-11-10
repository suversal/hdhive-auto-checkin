from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class Config:
    data_dir: Path
    public_url: str = ""
    secure_cookie: bool = False
    scheduler_interval: float = 1.0
    scheduler_enabled: bool = True
    open_browser: bool = False
    local_port: int = 8787
    web_dir: Path = Path(__file__).resolve().parent.parent / "web"

    @classmethod
    def from_env(cls) -> "Config":
        public = os.getenv("SHIKE_PUBLIC_URL", "").rstrip("/")
        return cls(
            data_dir=Path(os.getenv("SHIKE_DATA_DIR", "var/shike")).resolve(),
            public_url=public,
            secure_cookie=public.startswith("https://") or os.getenv("SHIKE_COOKIE_SECURE") == "1",
        )

    @property
    def allowed_hosts(self) -> list[str]:
        hosts = ["localhost", "127.0.0.1", "[::1]", "testserver"]
        if self.public_url:
            hosts.append(urlparse(self.public_url).hostname or "localhost")
        return hosts
