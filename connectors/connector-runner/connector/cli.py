"""connector-runner 命令行入口（argparse）。

子命令：
- pair：发起配对（POST /v1/pairings → 扫码 → 本机确认 → 兑换）并保存凭据
- run ：已配对则启动连接器 WSS 会话（自动心跳、执行 run、断线重连恢复）
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import platform as platform_mod
import sys

import httpx

from . import __version__
from .adapters import ADAPTER_KINDS, build_adapter
from .config import ConfigurationError, ServerConfig, load_credentials, save_credentials
from .ledger import Ledger
from .pairing import PairingClient, PairingError
from .tokens import SessionRevokedError, TokenManager
from .ws import CONNECT_CAPABILITIES, ConnectorSession


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="connector-runner", description="AIChat 外部 Agent 连接器（配对 + 执行运行层）"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    pair = sub.add_parser("pair", help="发起配对并兑换凭据")
    pair.add_argument("--agent-id", required=True, help="要绑定的 AI 账号 ID")
    pair.add_argument("--name", required=True, help="连接器名称（展示给 AI 所有者）")
    pair.add_argument("--adapter", choices=ADAPTER_KINDS, default="echo", help="适配器类型（默认 echo）")
    pair.add_argument("--server", help="AIChat 服务地址（或环境变量 AICHAT_SERVER_URL）")
    pair.add_argument("--platform", help="平台标识（默认自动探测）")
    pair.add_argument("--credentials", help="凭据文件路径（默认 ~/.aichat-connector/credentials.json）")
    pair.add_argument("--ledger", help="本地执行账本路径（默认与凭据同目录 ledger.sqlite3）")

    run = sub.add_parser("run", help="已配对：启动连接器 WSS 会话")
    run.add_argument("--server", help="AIChat 服务地址（默认沿用配对时地址或 AICHAT_SERVER_URL）")
    run.add_argument("--adapter", choices=ADAPTER_KINDS, help="适配器类型（默认沿用配对时的 adapter_kind）")
    run.add_argument("--credentials", help="凭据文件路径")
    run.add_argument("--ledger", help="本地执行账本路径")
    return parser


async def cmd_pair(args: argparse.Namespace) -> int:
    config = ServerConfig.load(args.server, args.credentials, args.ledger)
    async with httpx.AsyncClient(timeout=20.0) as http:
        client = PairingClient(config, http)
        credentials = await client.run_pairing(
            agent_id=args.agent_id,
            connector_name=args.name,
            adapter_kind=args.adapter,
            platform=args.platform or f"{platform_mod.system().lower()}-python",
            requested_capabilities=list(CONNECT_CAPABILITIES),
        )
    save_credentials(config.credentials_path, credentials)
    print(f"\n配对成功：connector_id={credentials['connector_id']} agent_id={credentials['agent_id']}")
    print(f"凭据已写入：{config.credentials_path}（权限 0600，Windows 上尽力而为）")
    print(f"执行账本：{config.ledger_path}")
    print("下一步：connector-runner run")
    return 0


async def cmd_run(args: argparse.Namespace) -> int:
    config = ServerConfig.load(args.server, args.credentials, args.ledger)
    credentials = load_credentials(config.credentials_path)
    if credentials is None:
        print(
            f"未找到配对凭据（{config.credentials_path}）。请先执行：connector-runner pair ...",
            file=sys.stderr,
        )
        return 2
    paired_server = credentials.get("server_base_url")
    if paired_server and paired_server != config.server_base_url:
        print(
            f"提示：--server（{config.server_base_url}）与配对时地址（{paired_server}）不一致，以 --server 为准。",
            file=sys.stderr,
        )
    adapter_kind = args.adapter or credentials.get("adapter_kind") or "echo"
    ledger = Ledger(config.ledger_path)
    adapter = build_adapter(adapter_kind, ledger=ledger)
    print(f"使用适配器：{adapter_kind}（连接器 {credentials.get('connector_id')}）")
    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            tokens = TokenManager(credentials, config.server_base_url, http)
            session = ConnectorSession(
                config=config,
                token_manager=tokens,
                ledger=ledger,
                adapter=adapter,
                http=http,
                adapter_kind=adapter_kind,
                connector_id=credentials["connector_id"],
            )
            await session.run_forever()  # 正常情况下一直运行
    finally:
        if hasattr(adapter, "aclose"):
            await adapter.aclose()
        ledger.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    )
    try:
        if args.command == "pair":
            return asyncio.run(cmd_pair(args))
        if args.command == "run":
            return asyncio.run(cmd_run(args))
        return 2
    except PairingError as exc:
        print(f"配对失败：{exc}", file=sys.stderr)
        return 1
    except SessionRevokedError as exc:
        print(f"{exc}\n请重新执行 connector-runner pair 完成配对。", file=sys.stderr)
        return 2
    except ConfigurationError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已退出。", file=sys.stderr)
        return 130
