"""ZCode CLI 适配器：托管一个可续接的 zcode 会话。

工作方式（2026-10-28 在 Ubuntu 24.04 上实测确认）：
- `zcode -p '<prompt>' --json` 每次都是**独立进程**，冷启动约 10 秒；
- 退出时返回 JSON，含 `sessionId`（形如 `sess_...`）与 `response`；
- `--resume <sessionId>` 能在**任意工作目录**下续接，上下文保持；
- `-p` 默认权限模式是 `yolo`（全自动批准），因此平台侧必须显式传 `--mode`。

因此本适配器不做"长驻进程接多轮"，而是"每次 spawn + 按 session_key 续接"。
会话 id 记在本地账本里，连接器重启后仍能接上。

注意：本适配器**不重放 context**。历史已经活在 zcode 自己的会话里，
重放会让 agent 看到重复内容。只发送最新一条用户消息。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import signal
from pathlib import Path
from typing import AsyncIterator

from ..config import ConfigurationError
from ..ledger import Ledger

log = logging.getLogger(__name__)

DEFAULT_BIN = "zcode"
DEFAULT_CWD = "~/aichat-workspace"
DEFAULT_MODE = "plan"  # 必须保守：`-p` 自身的默认是 yolo，不能让平台继承
VALID_MODES = ("plan", "edit", "build", "yolo", "guarded")


def _last_user_text(context: list[dict]) -> str:
    """取最新一条人类消息作为本次指令。"""
    for item in reversed(context):
        if item.get("sender_kind") != "ai":
            text = str(item.get("text") or "").strip()
            if text:
                return text
    # 全部是 AI 消息时退回最后一条非空文本
    for item in reversed(context):
        text = str(item.get("text") or "").strip()
        if text:
            return text
    return ""


def _parse_json_payload(output: str) -> dict | None:
    """从 CLI 输出中提取结果 JSON。

    stdout 可能混有噪声行（实测有 `ZCode Built-in skipped (not-due)`），
    因此逐行找最外层 JSON 对象，而不是整体 json.loads。
    """
    lines = output.splitlines()
    for start in range(len(lines)):
        if not lines[start].lstrip().startswith("{"):
            continue
        chunk = "\n".join(lines[start:]).strip()
        try:
            parsed = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and ("response" in parsed or "sessionId" in parsed):
            return parsed
    return None


class ZCodeAdapter:
    """把一个 zcode 会话托管成 AIChat 的 AI 后端。"""

    kind = "zcode"

    def __init__(
        self,
        *,
        ledger: Ledger,
        binary: str | None = None,
        cwd: str | None = None,
        mode: str | None = None,
        timeout: float = 1800.0,
    ) -> None:
        self._ledger = ledger
        self._binary = binary or os.environ.get("AICHAT_ZCODE_BIN") or DEFAULT_BIN
        self._cwd = Path(
            os.path.expanduser(cwd or os.environ.get("AICHAT_ZCODE_CWD") or DEFAULT_CWD)
        )
        requested_mode = mode or os.environ.get("AICHAT_ZCODE_MODE") or DEFAULT_MODE
        if requested_mode not in VALID_MODES:
            raise ConfigurationError(
                f"zcode 适配器权限模式非法：{requested_mode!r}（可选：{', '.join(VALID_MODES)}）"
            )
        self._mode = requested_mode
        self._timeout = timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._cancelled = False

    # ---------------------------------------------------------------- 环境检查

    def _resolve_policy(self, execution_policy: dict | None) -> tuple[str, Path]:
        """确定本次运行的权限模式与工作目录。

        服务端下发的 execution_policy 优先；缺失时退回本进程配置。
        模式永远以 PLAN 兜底而不是 yolo——`zcode -p` 自身默认全自动批准，
        如果这里漏判，用户以为只是聊天，实际文件已经被改了。
        """
        policy = execution_policy or {}
        mode = policy.get("permission_mode") or self._mode or DEFAULT_MODE
        if mode not in VALID_MODES:
            log.warning("服务端下发未知权限模式 %r，回退 %s", mode, DEFAULT_MODE)
            mode = DEFAULT_MODE
        workspace = policy.get("workspace_dir")
        cwd = Path(os.path.expanduser(workspace)) if workspace else self._cwd
        return mode, cwd

    def _ensure_cwd(self, cwd: Path | None = None) -> None:
        target = cwd or self._cwd
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigurationError(f"无法创建 zcode 工作目录 {target}：{exc}") from exc

    def _binary_argv(self) -> list[str]:
        """可执行文件及其固定前置参数。

        binary 可以是单个路径，也可以是 argv 列表（测试替身、
        `python -m` 形式或包装脚本）。字符串形式按 POSIX 规则切分。
        """
        spec = self._binary
        if isinstance(spec, (list, tuple)):
            return [str(part) for part in spec]
        return shlex.split(spec, posix=os.name != "nt")

    def _build_args(
        self, prompt: str, resume_id: str | None, mode: str, cwd: Path
    ) -> list[str]:
        args = [*self._binary_argv(), "-p", prompt, "--json",
                "--mode", mode, "--cwd", str(cwd)]
        if resume_id:
            args.extend(["--resume", resume_id])
        return args

    # ---------------------------------------------------------------- 会话索引

    def _session_key(self, session_key: str | None) -> str:
        return session_key or "__default__"

    def _resume_id_for(self, key: str) -> str | None:
        record = self._ledger.get_session(key, self.kind)
        return record.external_session_id if record is not None else None

    # ---------------------------------------------------------------- 主流程

    async def run(
        self,
        context: list[dict],
        system_prompt: str | None,
        session_key: str | None = None,
        execution_policy: dict | None = None,
    ) -> AsyncIterator[str]:
        self._cancelled = False
        mode, cwd = self._resolve_policy(execution_policy)
        self._ensure_cwd(cwd)
        prompt = _last_user_text(context)
        if not prompt:
            yield "（没有可执行的指令内容）"
            return

        key = self._session_key(session_key)
        resume_id = self._resume_id_for(key)

        result = await self._invoke(prompt, resume_id, mode, cwd)
        if result is None:
            return
        if self._cancelled:
            return

        payload = result.get("payload")
        if payload is None:
            # 续接失败（会话被清理、版本变化等）：丢弃索引后新建会话重试一次
            if resume_id:
                log.warning("zcode 会话续接失败（%s），改为新建会话", resume_id)
                self._ledger.clear_session(key, self.kind)
                result = await self._invoke(prompt, None, mode, cwd)
                if result is None or self._cancelled:
                    return
                payload = result.get("payload")

        if payload is None:
            stderr = (result.get("stderr") or "").strip()
            log.error("zcode 输出无法解析：exit=%s stderr=%s", result.get("returncode"), stderr[:400])
            yield "执行失败：无法解析 zcode 输出"
            return

        session_id = payload.get("sessionId")
        if isinstance(session_id, str) and session_id:
            self._ledger.save_session(
                key, self.kind, external_session_id=session_id, cwd=str(cwd)
            )

        text = payload.get("response")
        if isinstance(text, str) and text:
            yield text
        elif payload.get("error"):
            yield f"执行失败：{payload['error']}"

    async def _invoke(
        self, prompt: str, resume_id: str | None, mode: str, cwd: Path
    ) -> dict | None:
        """跑一次 zcode；返回 {payload, stderr, returncode}。被取消时返回 None。"""
        args = self._build_args(prompt, resume_id, mode, cwd)
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
                # 独立进程组：取消时可以连带杀掉它派生的子进程
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise ConfigurationError(
                f"找不到 zcode 可执行文件：{self._binary}（设置 AICHAT_ZCODE_BIN）"
            ) from exc
        self._proc = proc
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except TimeoutError:
            await self._kill()
            log.error("zcode 超时（%.0fs）", self._timeout)
            return None
        except asyncio.CancelledError:
            await self._kill()
            raise
        finally:
            self._proc = None

        if self._cancelled:
            return None

        decoded = stdout.decode("utf-8", "replace")
        return {
            "payload": _parse_json_payload(decoded),
            "stderr": stderr.decode("utf-8", "replace"),
            "returncode": proc.returncode,
        }

    async def _kill(self) -> None:
        """杀掉整个进程组，避免 zcode 派生的子进程变成孤儿。"""
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
        except OSError:
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except TimeoutError:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass

    def cancel(self) -> None:
        """请求取消：标记后由 _invoke 的取消路径杀进程组。"""
        self._cancelled = True
        proc = self._proc
        if proc is not None and proc.returncode is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
