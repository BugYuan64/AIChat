"""配对客户端（契约 contracts/PROTOCOL.md §7）。

流程：POST /v1/pairings → 终端展示 ASCII 二维码 + short_code + confirm_code →
按 interval_seconds 轮询 POST /v1/pairing-status（device_code 放 body；SLOW_DOWN 按
retry_after_ms 退避）→ pending_local 时打印 owner/agent 名与 confirm_code，本机输入 y 确认 →
POST /v1/pairing-local-confirmation → POST /v1/pairing-token 兑换凭据。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal

import httpx
import qrcode
from pydantic import BaseModel, Field

from .client import (
    ApiError,
    PAIRING_ERROR_STATUS,
    PAIRING_TERMINAL_STATUSES,
    THROTTLE_CODES,
    parse_envelope,
    post_json,
)
from .config import ServerConfig

PollAction = Literal[
    "wait",
    "slow_down",
    "pending_local",
    "approved",
    "redeemed",
    "denied",
    "expired",
    "cancelled",
    "revoked",
    "consumed",
]

# 服务端状态机允许上报的状态（未知枚举值必须拒绝）
KNOWN_PAIRING_STATUSES = frozenset(
    {"pending_user", "pending_local", "approved", "redeemed", "denied", "expired", "cancelled"}
)

# 终态 → 给操作者的清晰提示
TERMINAL_MESSAGES = {
    "denied": "配对已被 AI 所有者拒绝（denied）。",
    "expired": "配对已过期（expired），请重新发起。",
    "cancelled": "配对已被取消（cancelled）。",
    "revoked": "配对已被撤销（revoked）。",
    "consumed": "配对已被兑换（consumed），凭据不会再次下发；请重新发起配对。",
    "redeemed": "配对已被兑换（redeemed）。若非本机所为，请检查环境并重新配对。",
}


class PairingError(Exception):
    """配对失败（终态或协议异常）。"""


class PairingAborted(PairingError):
    """本机操作者拒绝确认。"""


class PairingCreated(BaseModel):
    """POST /v1/pairings 的 201 响应。"""

    pairing_id: str
    short_code: str
    qr_payload: str
    confirm_code: str
    device_code: str = Field(repr=False)  # 秘密：不进日志
    expires_at: str
    interval_seconds: float = 5.0


class PairingCredentials(BaseModel):
    """POST /v1/pairing-token 的一次性兑换响应。"""

    connector_id: str
    agent_id: str
    access_token: str = Field(repr=False)
    refresh_credential: str = Field(repr=False)
    expires_in: int


@dataclass(frozen=True)
class PollResult:
    """一次 /v1/pairing-status 轮询的解析结果（下一步动作）。"""

    action: PollAction
    retry_after_ms: int | None = None
    owner_display_name: str | None = None
    agent_display_name: str | None = None
    confirm_code: str | None = None

    @property
    def terminal(self) -> bool:
        return self.action in PAIRING_TERMINAL_STATUSES


def interpret_poll(payload: object) -> PollResult:
    """把 /v1/pairing-status 的一次响应（成功或错误信封）解析为下一步动作。

    纯函数，便于单元测试。未知状态/未知错误码一律抛 PairingError（契约：未知枚举值必须拒绝）。
    """
    if isinstance(payload, dict) and "error" in payload:
        try:
            parse_envelope(payload)  # 必然抛 ApiError
        except ApiError as err:
            if err.code in THROTTLE_CODES:
                return PollResult(action="slow_down", retry_after_ms=err.retry_after_ms)
            if err.code in PAIRING_ERROR_STATUS:
                status = PAIRING_ERROR_STATUS[err.code]
                if status == "pending_user":
                    return PollResult(action="wait")
                return PollResult(action=status)  # type: ignore[arg-type]
            raise PairingError(f"配对状态查询失败：[{err.code}] {err.message}") from err

    try:
        data = parse_envelope(payload)
    except ApiError as err:
        raise PairingError(f"配对状态响应不合法：{err}") from err

    status = data.get("status")
    if status not in KNOWN_PAIRING_STATUSES:
        raise PairingError(f"服务端返回未知配对状态：{status!r}")
    if status == "pending_user":
        return PollResult(action="wait")
    if status == "pending_local":
        return PollResult(
            action="pending_local",
            owner_display_name=data.get("owner_display_name"),
            agent_display_name=data.get("agent_display_name"),
            confirm_code=data.get("confirm_code"),
        )
    if status == "approved":
        return PollResult(action="approved")
    # redeemed / denied / expired / cancelled：终态
    return PollResult(action=status)  # type: ignore[arg-type]


def next_poll_delay(interval_seconds: float, result: PollResult) -> float:
    """计算下一次轮询的等待秒数：SLOW_DOWN 按 retry_after_ms，否则按服务端间隔。"""
    if result.action == "slow_down":
        if result.retry_after_ms is not None:
            return max(1.0, result.retry_after_ms / 1000.0)
        return interval_seconds * 2
    return interval_seconds


def _parse_rfc3339(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _print_qr_default(payload: str) -> None:
    """终端打印 ASCII 二维码（只含配对入口与非秘密短码）。"""
    try:
        qr = qrcode.QRCode(border=1)
        qr.add_data(payload)
        qr.print_ascii(tty=False)
    except Exception:  # 终端编码等异常时退化为展示链接
        print(f"（无法渲染二维码，请手动打开）{payload}")


def _default_confirm_prompt(detail: str) -> bool:
    answer = input(f"{detail}\n确认绑定？输入 y 继续: ").strip().lower()
    return answer in {"y", "yes"}


class PairingClient:
    """执行完整配对流程，成功时返回凭据字典（含元信息）。"""

    def __init__(
        self,
        config: ServerConfig,
        http: httpx.AsyncClient,
        *,
        confirm_prompt: Callable[[str], bool] | None = None,
        render_qr: Callable[[str], None] | None = None,
        sleep: Callable[[float], object] = asyncio.sleep,
        output: Callable[[str], None] = print,
    ) -> None:
        self._config = config
        self._http = http
        self._base = config.server_base_url
        self._confirm_prompt = confirm_prompt or _default_confirm_prompt
        self._render_qr = render_qr or _print_qr_default
        self._sleep = sleep
        self._print = output

    async def run_pairing(
        self,
        *,
        agent_id: str,
        connector_name: str,
        adapter_kind: str,
        platform: str,
        requested_capabilities: list[str] | None = None,
    ) -> dict:
        """发起配对并阻塞直到兑换成功或终态；返回应写入凭据文件的字典。"""
        body = {
            "agent_id": agent_id,
            "connector_name": connector_name,
            "platform": platform,
            "adapter_kind": adapter_kind,
            "requested_capabilities": requested_capabilities or [],
        }
        try:
            data = await post_json(self._http, f"{self._base}/v1/pairings", json_body=body)
        except ApiError as err:
            raise PairingError(f"创建配对请求失败：{err}") from err
        try:
            created = PairingCreated.model_validate(data)
        except Exception as exc:
            raise PairingError(f"配对响应不合法：{exc}") from exc

        expires_at = _parse_rfc3339(created.expires_at)
        self._print(
            f"\n配对请求已创建（pairing_id={created.pairing_id}），"
            f"有效期至 {created.expires_at}。请用已登录的 AIChat App 扫码批准。"
        )
        self._render_qr(created.qr_payload)
        self._print(f"短码 short_code  : {created.short_code}")
        self._print(f"确认码 confirm_code: {created.confirm_code}")

        return await self._poll_until_redeemed(created, adapter_kind)

    async def _poll_until_redeemed(self, created: PairingCreated, adapter_kind: str) -> dict:
        interval = created.interval_seconds or 5.0
        delay = interval
        deadline = _parse_rfc3339(created.expires_at) + timedelta(seconds=2)  # 以服务端状态为准，本地兜底
        while True:
            await self._sleep(delay)
            if datetime.now(timezone.utc) > deadline:
                raise PairingError(TERMINAL_MESSAGES["expired"])

            payload = await self._post_status_raw(created.device_code)
            result = interpret_poll(payload)
            delay = next_poll_delay(interval, result)

            if result.action in {"wait", "slow_down"}:
                continue
            if result.action == "pending_local":
                await self._local_confirmation(created, result)
                continue
            if result.action == "approved":
                return await self._redeem(created.device_code, adapter_kind)
            if result.terminal:
                raise PairingError(TERMINAL_MESSAGES[result.action])
            raise PairingError(f"未知轮询动作：{result.action!r}")  # pragma: no cover

    async def _post_status_raw(self, device_code: str) -> object:
        """POST /v1/pairing-status；device_code 只放请求体，不打日志。"""
        resp = await self._http.post(
            f"{self._base}/v1/pairing-status", json={"device_code": device_code}
        )
        try:
            return resp.json()
        except ValueError as exc:
            raise PairingError(f"配对状态响应不是 JSON（HTTP {resp.status_code}）") from exc

    async def _local_confirmation(self, created: PairingCreated, result: PollResult) -> None:
        """pending_local：打印 owner/agent 与确认码，等本机操作者输入 y 确认。"""
        confirm_code = result.confirm_code
        if confirm_code is not None and confirm_code != created.confirm_code:
            raise PairingError(
                f"确认码不一致（服务端 {confirm_code} != 创建时 {created.confirm_code}），疑似异常，已中止配对。"
            )
        detail = (
            "\n== 需要本机确认 ==\n"
            f"  所有者: {result.owner_display_name}\n"
            f"  AI    : {result.agent_display_name}\n"
            f"  确认码: {confirm_code}\n"
            "请核对以上信息与 App 端一致后，在本机输入 y 完成确认。"
        )
        self._print(detail)
        if not self._confirm_prompt(detail):
            raise PairingAborted("本机未确认，配对中止（服务端记录将在到期后失效）。")
        try:
            await post_json(
                self._http,
                f"{self._base}/v1/pairing-local-confirmation",
                json_body={"device_code": created.device_code, "confirmed": True},
            )
        except ApiError as err:
            raise PairingError(f"本机确认提交失败：{err}") from err
        self._print("本机确认已提交，等待兑换令牌…")

    async def _redeem(self, device_code: str, adapter_kind: str) -> dict:
        """POST /v1/pairing-token 一次性兑换。"""
        try:
            data = await post_json(
                self._http, f"{self._base}/v1/pairing-token", json_body={"device_code": device_code}
            )
        except ApiError as err:
            if err.code in {"PAIRING_CONSUMED"}:
                raise PairingError(TERMINAL_MESSAGES["consumed"]) from err
            if err.code in {"PAIRING_EXPIRED"}:
                raise PairingError(TERMINAL_MESSAGES["expired"]) from err
            raise PairingError(f"兑换配对令牌失败：{err}") from err
        try:
            creds = PairingCredentials.model_validate(data)
        except Exception as exc:
            raise PairingError(f"兑换响应不合法：{exc}") from exc
        result = creds.model_dump()
        result.update(
            {
                "server_base_url": self._base,
                "adapter_kind": adapter_kind,
                "paired_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return result
