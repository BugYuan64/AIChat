"""运行配置：服务地址、凭据存储路径、本地账本路径。

取值优先级：CLI 参数 > 环境变量 > 默认值。
环境变量：AICHAT_SERVER_URL / AICHAT_CREDENTIALS_PATH / AICHAT_LEDGER_PATH。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CREDENTIALS_PATH = Path.home() / ".aichat-connector" / "credentials.json"


class ConfigurationError(Exception):
    """配置缺失或不合法。"""


@dataclass(frozen=True)
class ServerConfig:
    """连接器运行所需的全部路径与地址。"""

    server_base_url: str
    credentials_path: Path
    ledger_path: Path

    @classmethod
    def load(
        cls,
        server_base_url: str | None = None,
        credentials_path: str | Path | None = None,
        ledger_path: str | Path | None = None,
    ) -> "ServerConfig":
        server = (
            server_base_url
            or os.environ.get("AICHAT_SERVER_URL")
            or os.environ.get("AICHAT_CONNECTOR_SERVER")
            or ""
        ).strip().rstrip("/")
        if not server:
            raise ConfigurationError(
                "缺少 AIChat 服务地址：传 --server 或设置环境变量 AICHAT_SERVER_URL"
            )
        if not server.startswith(("http://", "https://")):
            raise ConfigurationError("服务地址必须以 http:// 或 https:// 开头")

        credentials = Path(
            credentials_path
            or os.environ.get("AICHAT_CREDENTIALS_PATH")
            or DEFAULT_CREDENTIALS_PATH
        )
        ledger = Path(
            ledger_path
            or os.environ.get("AICHAT_LEDGER_PATH")
            or credentials.with_name("ledger.sqlite3")
        )
        return cls(server_base_url=server, credentials_path=credentials, ledger_path=ledger)


def load_credentials(path: str | Path) -> dict | None:
    """读取配对凭据；文件不存在返回 None。"""
    path = Path(path)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"凭据文件无法读取（{path}）：{exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"凭据文件格式不合法（{path}）")
    return data


def save_credentials(path: str | Path, credentials: dict) -> None:
    """把凭据写入受限权限文件（0600；Windows 上尽力而为）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 以 0600 创建（POSIX 生效；Windows 上由后续 chmod 尽力而为）
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fp:
        json.dump(credentials, fp, ensure_ascii=False, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows 上 chmod 支持有限，忽略即可（创建时已尽量受限）
        pass
