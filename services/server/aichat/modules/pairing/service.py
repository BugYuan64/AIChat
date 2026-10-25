"""pairing 模块：连接器扫码绑定设备流。

pending_user → pending_local → approved → redeemed；非终态可转 denied/expired/cancelled。
device_code 只存哈希且仅在创建响应出现一次；兑换在一个事务内完成
（创建 connector、更新 RuntimeBinding generation、撤销旧连接器与在途运行）。
"""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.context import AppContext
from aichat.core.errors import ApiError, forbidden, not_found, rate_limited, validation_failed, version_conflict
from aichat.core.ids import new_id
from aichat.core.security import (
    create_access_token,
    constant_time_eq,
    random_code,
    random_digits,
    random_token,
    sha256_hex,
    utcnow,
)
from aichat.modules.agents.models import AgentProfile, RuntimeBinding
from aichat.modules.audit.service import AuditService
from aichat.modules.identity.models import Account
from aichat.modules.pairing.models import Connector, PairingSession

TERMINAL_PAIRING_STATES = {"redeemed", "denied", "expired", "cancelled"}


class PairingService:
    def __init__(self, ctx: AppContext, session: AsyncSession) -> None:
        self.ctx = ctx
        self.settings = ctx.settings
        self.session = session
        self.audit = AuditService(session)

    def _refresh_pairing(self, pairing: PairingSession) -> None:
        """惰性过期：所有非终态受原到期限制。"""
        if pairing.status not in TERMINAL_PAIRING_STATES and pairing.expires_at <= utcnow():
            pairing.status = "expired"

    async def create_pairing(self, body, *, client_ip: str = "") -> dict:
        self.ctx.limiter.check(f"pairing:{client_ip or body.agent_id}", self.settings.rate_limit_pairing_per_min)
        agent = await self.session.get(Account, body.agent_id)
        if agent is None or agent.kind != "ai" or agent.status != "active":
            raise not_found("AI 账号不存在")
        profile = await self.session.get(AgentProfile, agent.id)
        if profile is None:
            raise not_found("AI 档案不存在")
        device_code = random_token(32)
        short_code = random_code(self.settings.short_code_alphabet, self.settings.short_code_length)
        confirm_code = random_digits(self.settings.confirm_code_length)
        pairing = PairingSession(
            id=new_id(),
            agent_account_id=agent.id,
            connector_name=body.connector_name,
            platform=body.platform,
            adapter_kind=body.adapter_kind,
            requested_capabilities=body.requested_capabilities,
            short_code_hash=sha256_hex(short_code),
            confirm_code=confirm_code,
            device_code_hash=sha256_hex(device_code),
            expires_at=utcnow() + timedelta(seconds=self.settings.pairing_ttl_seconds),
        )
        self.session.add(pairing)
        await self.session.flush()
        base = (self.settings.public_base_url or "https://pair.aichat.local").rstrip("/")
        return {
            "pairing_id": pairing.id,
            "short_code": short_code,
            "confirm_code": confirm_code,
            "qr_payload": f"{base}/pair?pid={pairing.id}&code={short_code}",
            "device_code": device_code,
            "expires_at": pairing.expires_at.isoformat() + "Z",
            "interval_seconds": self.settings.pairing_poll_seconds,
        }

    async def get_pairing_for_app(self, pairing_id: str, short_code: str) -> dict:
        pairing = await self._by_id_and_code(pairing_id, short_code)
        agent = await self.session.get(Account, pairing.agent_account_id)
        profile = await self.session.get(AgentProfile, pairing.agent_account_id)
        owner = await self.session.get(Account, profile.owner_account_id) if profile else None
        from aichat.modules.pairing.schemas import pairing_public_out

        return pairing_public_out(pairing, agent, owner)

    async def _by_id_and_code(self, pairing_id: str, short_code: str) -> PairingSession:
        pairing = await self.session.get(PairingSession, pairing_id)
        if pairing is None or not constant_time_eq(pairing.short_code_hash, sha256_hex(short_code)):
            raise not_found("配对请求不存在")
        self._refresh_pairing(pairing)
        return pairing

    async def decide(self, pairing_id: str, decider_id: str, approve: bool, confirm_code: str,
                     expected_version: int) -> dict:
        pairing = await self.session.get(PairingSession, pairing_id)
        if pairing is None:
            raise not_found("配对请求不存在")
        self._refresh_pairing(pairing)
        profile = await self.session.get(AgentProfile, pairing.agent_account_id)
        if profile is None or profile.owner_account_id != decider_id:
            raise not_found("配对请求不存在")  # 跨所有者不泄漏存在性
        if pairing.status == "pending_local" and approve:
            return {"pairing_id": pairing.id, "status": pairing.status, "version": str(pairing.version)}
        if pairing.status not in ("pending_user",):
            raise ApiError(400, _pairing_code(pairing.status), f"配对请求状态为 {pairing.status}")
        if pairing.version != expected_version:
            raise version_conflict()
        if not constant_time_eq(pairing.confirm_code, confirm_code):
            raise validation_failed("确认码不匹配")
        pairing.version += 1
        if approve:
            pairing.status = "pending_local"
            pairing.decided_by = decider_id
            pairing.decided_at = utcnow()
        else:
            pairing.status = "denied"
            pairing.decided_by = decider_id
            pairing.decided_at = utcnow()
        await self.audit.record("pairing.decide", "pairing", pairing.id, actor_account_id=decider_id,
                                summary={"decision": pairing.status, "agent": pairing.agent_account_id})
        return {"pairing_id": pairing.id, "status": pairing.status, "version": str(pairing.version)}

    async def _by_device_code(self, device_code: str) -> PairingSession:
        pairing = await self.session.scalar(
            select(PairingSession).where(PairingSession.device_code_hash == sha256_hex(device_code))
        )
        if pairing is None:
            raise not_found("配对请求不存在")
        self._refresh_pairing(pairing)
        return pairing

    async def poll_status(self, device_code: str) -> dict:
        pairing = await self._by_device_code(device_code)
        out: dict = {"status": pairing.status}
        if pairing.status == "pending_local":
            profile = await self.session.get(AgentProfile, pairing.agent_account_id)
            owner = await self.session.get(Account, profile.owner_account_id) if profile else None
            agent = await self.session.get(Account, pairing.agent_account_id)
            out["owner_display_name"] = owner.display_name if owner else None
            out["agent_display_name"] = agent.display_name if agent else None
            out["confirm_code"] = pairing.confirm_code
        if pairing.status in TERMINAL_PAIRING_STATES - {"redeemed"}:
            raise ApiError(400, _pairing_code(pairing.status), f"配对已结束：{pairing.status}")
        return out

    async def local_confirm(self, device_code: str, confirmed: bool) -> dict:
        pairing = await self._by_device_code(device_code)
        if pairing.status != "pending_local":
            raise ApiError(400, _pairing_code(pairing.status), f"配对请求状态为 {pairing.status}")
        if not confirmed:
            pairing.status = "cancelled"
            await self.audit.record("pairing.cancel_local", "pairing", pairing.id)
            return {"status": pairing.status}
        pairing.status = "approved"
        pairing.local_confirmed_at = utcnow()
        await self.audit.record("pairing.local_confirm", "pairing", pairing.id)
        return {"status": pairing.status}

    async def redeem_token(self, device_code: str) -> dict:
        """一次性兑换：赢者得到唯一一次明文凭据；败者 409 PAIRING_CONSUMED。"""
        pairing = await self._by_device_code(device_code)
        if pairing.status == "redeemed":
            raise ApiError(409, "PAIRING_CONSUMED", "配对会话已兑换")
        if pairing.status != "approved":
            raise ApiError(400, _pairing_code(pairing.status), f"配对请求状态为 {pairing.status}")
        # Claim with one conditional write. A read followed by an ORM assignment
        # lets concurrent requests both issue credentials before either commits.
        redeemed_at = utcnow()
        claimed = await self.session.scalar(
            update(PairingSession).where(
                PairingSession.id == pairing.id,
                PairingSession.status == "approved",
                PairingSession.expires_at > redeemed_at,
            ).values(status="redeemed", redeemed_at=redeemed_at)
            .returning(PairingSession.id).execution_options(synchronize_session=False)
        )
        if claimed is None:
            raise ApiError(409, "PAIRING_CONSUMED", "配对会话已兑换或状态已变更")
        # Serialize distinct approved pairings for one AI on PostgreSQL too.
        profile = await self.session.scalar(
            select(AgentProfile).where(AgentProfile.account_id == pairing.agent_account_id)
            .with_for_update()
        )
        if profile is None:
            raise not_found("AI 档案不存在")

        # 撤销旧连接器与在途运行
        old_connector = await self.session.scalar(
            select(Connector).where(
                Connector.agent_account_id == pairing.agent_account_id,
                Connector.revoked_at.is_(None),
            )
        )
        if old_connector is not None:
            old_connector.revoked_at = utcnow()
            old_connector.status = "revoked"
            old_connector.refresh_hash = None

        refresh_credential = random_token(32)
        connector = Connector(
            id=new_id(),
            agent_account_id=pairing.agent_account_id,
            owner_account_id=profile.owner_account_id,
            name=pairing.connector_name,
            platform=pairing.platform,
            adapter_kind=pairing.adapter_kind,
            capabilities=pairing.requested_capabilities or [],
            refresh_hash=sha256_hex(refresh_credential),
        )
        self.session.add(connector)
        await self.session.flush()

        from aichat.modules.agents.service import AgentsService

        agents = AgentsService(self.ctx, self.session)
        old_binding = await self.session.get(RuntimeBinding, pairing.agent_account_id)
        generation = (old_binding.generation + 1) if old_binding is not None else 1
        if old_binding is not None:
            await agents._revoke_inflight(pairing.agent_account_id)
            await self.session.delete(old_binding)
            await self.session.flush()
        binding = RuntimeBinding(
            agent_account_id=pairing.agent_account_id,
            mode="connector",
            connector_id=connector.id,
            capabilities=connector.capabilities,
            generation=generation,
            enabled=True,
        )
        self.session.add(binding)
        connector.binding_generation = generation

        pairing.status = "redeemed"
        pairing.redeemed_at = redeemed_at

        access_token, _ = create_access_token(
            self.settings,
            subject_type="connector",
            subject_id=connector.id,
            audience="connector",
            expires_in=self.settings.connector_access_token_seconds,
            extra_claims={
                "agent_id": connector.agent_account_id,
                "owner_id": connector.owner_account_id,
                "cred_ver": connector.credential_version,
            },
        )
        await self.audit.record("pairing.redeem", "connector", connector.id,
                                summary={"agent": connector.agent_account_id,
                                         "generation": generation})
        return {
            "connector_id": connector.id,
            "agent_id": connector.agent_account_id,
            "access_token": access_token,
            "refresh_credential": refresh_credential,
            "expires_in": self.settings.connector_access_token_seconds,
        }

    async def refresh_access_token(self, refresh_credential: str) -> dict:
        connector = await self.session.scalar(
            select(Connector).where(Connector.refresh_hash == sha256_hex(refresh_credential))
        )
        if connector is None or connector.revoked_at is not None:
            raise forbidden("连接器凭据无效")
        access_token, _ = create_access_token(
            self.settings,
            subject_type="connector",
            subject_id=connector.id,
            audience="connector",
            expires_in=self.settings.connector_access_token_seconds,
            extra_claims={
                "agent_id": connector.agent_account_id,
                "owner_id": connector.owner_account_id,
                "cred_ver": connector.credential_version,
            },
        )
        return {"access_token": access_token, "expires_in": self.settings.connector_access_token_seconds}

    async def revoke_connector(self, connector_id: str, actor_id: str, reason: str | None) -> dict:
        connector = await self.session.get(Connector, connector_id)
        if connector is None:
            raise not_found("连接器不存在")
        profile = await self.session.get(AgentProfile, connector.agent_account_id)
        if profile is None or profile.owner_account_id != actor_id:
            raise forbidden("只有 AI 所有者可以撤销连接器")
        connector.revoked_at = utcnow()
        connector.status = "revoked"
        connector.refresh_hash = None
        binding = await self.session.get(RuntimeBinding, connector.agent_account_id)
        if binding is not None and binding.connector_id == connector_id:
            binding.enabled = False
            binding.generation += 1
            from aichat.modules.agents.service import AgentsService

            agents = AgentsService(self.ctx, self.session)
            await agents._revoke_inflight(connector.agent_account_id)
        await self.audit.record("connector.revoke", "connector", connector_id,
                                actor_account_id=actor_id, summary={"reason": reason})
        return {"revoked_at": connector.revoked_at.isoformat() + "Z"}

    async def list_connectors(self, agent_account_id: str, owner_id: str) -> list[dict]:
        profile = await self.session.get(AgentProfile, agent_account_id)
        if profile is None or profile.owner_account_id != owner_id:
            raise forbidden("只有 AI 所有者可以查看连接器")
        rows = list(await self.session.scalars(
            select(Connector).where(Connector.agent_account_id == agent_account_id)
        ))
        return [
            {
                "connector_id": r.id,
                "name": r.name,
                "platform": r.platform,
                "adapter_kind": r.adapter_kind,
                "status": r.status,
                "credential_version": str(r.credential_version),
                "binding_generation": str(r.binding_generation),
                "last_seen_at": r.last_seen_at.isoformat() + "Z" if r.last_seen_at else None,
                "revoked_at": r.revoked_at.isoformat() + "Z" if r.revoked_at else None,
            }
            for r in rows
        ]


def _pairing_code(status: str) -> str:
    return {
        "denied": "PAIRING_DENIED",
        "expired": "PAIRING_EXPIRED",
        "cancelled": "PAIRING_REVOKED",
        "pending_user": "PAIRING_PENDING",
        "pending_local": "PAIRING_PENDING",
        "approved": "PAIRING_PENDING",
        "redeemed": "PAIRING_CONSUMED",
    }.get(status, "PAIRING_EXPIRED")
