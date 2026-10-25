"""agents 模块：AI 档案、模型绑定（加密凭据+连接测试）、使用授权、供应商白名单。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.context import AppContext
from aichat.core.errors import forbidden, not_found, validation_failed
from aichat.core.ids import new_id
from aichat.core.outbox import emit
from aichat.core.security import utcnow
from aichat.modules.agents.models import (
    AgentGrant,
    AgentProfile,
    ProviderCredential,
    ProviderEndpoint,
    RuntimeBinding,
)
from aichat.modules.audit.service import AuditService
from aichat.modules.identity.models import Account
from aichat.runtime.base import ModelCallSpec
from aichat.runtime.model_api import test_connection


class AgentsService:
    def __init__(self, ctx: AppContext, session: AsyncSession) -> None:
        self.ctx = ctx
        self.settings = ctx.settings
        self.session = session
        self.audit = AuditService(session)

    # ---- 档案 ----

    async def create_agent(self, owner_id: str, handle: str, display_name: str, bio: str | None) -> Account:
        dup = await self.session.scalar(select(Account).where(Account.handle == handle))
        if dup is not None:
            raise validation_failed("账号名已被占用")
        account = Account(id=new_id(), kind="ai", handle=handle, display_name=display_name, bio=bio)
        self.session.add(account)
        self.session.add(AgentProfile(account_id=account.id, owner_account_id=owner_id))
        # 所有者自动获得使用授权
        self.session.add(AgentGrant(id=new_id(), agent_account_id=account.id, human_account_id=owner_id))
        await self.audit.record("agent.create", "agent", account.id, actor_account_id=owner_id,
                                summary={"handle": handle})
        return account

    async def require_owner(self, agent_account_id: str, actor_id: str) -> AgentProfile:
        profile = await self.session.get(AgentProfile, agent_account_id)
        if profile is None:
            raise not_found("AI 不存在")
        if profile.owner_account_id != actor_id:
            raise forbidden("只有 AI 所有者可以执行该操作")
        return profile

    async def get_agent_view(self, agent_account_id: str, viewer_id: str) -> dict:
        from aichat.modules.agents.schemas import agent_out
        from aichat.modules.pairing.models import Connector

        account = await self.session.get(Account, agent_account_id)
        if account is None or account.kind != "ai":
            raise not_found("AI 不存在")
        profile = await self.session.get(AgentProfile, agent_account_id)
        binding = await self.session.get(RuntimeBinding, agent_account_id)
        connector = None
        if binding is not None and binding.connector_id:
            connector = await self.session.get(Connector, binding.connector_id)
        is_owner = profile is not None and profile.owner_account_id == viewer_id
        out = agent_out(account, profile, binding, connector)
        if not is_owner:
            out.pop("binding", None)  # 非所有者不看绑定细节，只看在线状态
            out["connector_online"] = connector.status in ("online", "ready") if connector else False
        return out

    async def list_owned(self, owner_id: str) -> list[dict]:
        rows = list(await self.session.scalars(
            select(AgentProfile).where(AgentProfile.owner_account_id == owner_id)
        ))
        from aichat.modules.agents.schemas import agent_out
        from aichat.modules.pairing.models import Connector

        items = []
        for profile in rows:
            account = await self.session.get(Account, profile.account_id)
            binding = await self.session.get(RuntimeBinding, profile.account_id)
            connector = await self.session.get(Connector, binding.connector_id) if binding and binding.connector_id else None
            items.append(agent_out(account, profile, binding, connector))
        return items

    # ---- 模型绑定 ----

    async def set_model_binding(
        self, agent_account_id: str, owner_id: str, provider_code: str, credential: str,
        model_name: str, system_prompt: str | None, test: bool,
    ) -> RuntimeBinding:
        await self.require_owner(agent_account_id, owner_id)
        endpoint = await self.session.get(ProviderEndpoint, provider_code)
        if endpoint is None or not endpoint.enabled:
            raise validation_failed("供应商不在白名单或未启用")

        credential_row = ProviderCredential(
            id=new_id(), owner_account_id=owner_id, provider_code=provider_code,
            ciphertext=self.ctx.cipher.encrypt(credential),
        )
        self.session.add(credential_row)
        await self.session.flush()

        test_ok_at = None
        if test:
            spec = ModelCallSpec(base_url=endpoint.base_url, api_key=credential, model=model_name,
                                 system_prompt=None, timeout_seconds=30)
            try:
                await test_connection(spec)
            except Exception as exc:
                raise validation_failed(f"连接测试失败：{exc}")
            test_ok_at = utcnow()

        old = await self.session.get(RuntimeBinding, agent_account_id)
        generation = (old.generation + 1) if old is not None else 1
        if old is not None:
            await self._revoke_inflight(agent_account_id)
            await self.session.delete(old)
            await self.session.flush()
        binding = RuntimeBinding(
            agent_account_id=agent_account_id,
            mode="model_api",
            provider_code=provider_code,
            credential_id=credential_row.id,
            model_name=model_name,
            system_prompt=system_prompt,
            generation=generation,
            enabled=True,
            test_ok_at=test_ok_at or utcnow(),
        )
        self.session.add(binding)
        await emit(self.session, "binding.changed",
                   {"agent_account_id": agent_account_id, "mode": "model_api",
                    "generation": str(generation), "enabled": binding.enabled},
                   subject_account_ids=[owner_id])
        await self.audit.record("binding.set", "agent", agent_account_id, actor_account_id=owner_id,
                                summary={"mode": "model_api", "provider": provider_code,
                                         "generation": generation})
        return binding

    async def revoke_binding(self, agent_account_id: str, owner_id: str) -> None:
        await self.require_owner(agent_account_id, owner_id)
        binding = await self.session.get(RuntimeBinding, agent_account_id)
        if binding is None:
            raise not_found("没有生效的绑定")
        await self._revoke_inflight(agent_account_id)
        binding.generation += 1
        binding.enabled = False
        if binding.connector_id:
            from aichat.modules.pairing.models import Connector

            connector = await self.session.get(Connector, binding.connector_id)
            if connector is not None:
                connector.revoked_at = utcnow()
                connector.status = "revoked"
                connector.refresh_hash = None
        await emit(self.session, "binding.changed",
                   {"agent_account_id": agent_account_id, "generation": str(binding.generation),
                    "enabled": False},
                   subject_account_ids=[owner_id])
        await self.audit.record("binding.revoke", "agent", agent_account_id, actor_account_id=owner_id,
                                summary={"generation": binding.generation})

    async def _revoke_inflight(self, agent_account_id: str) -> None:
        """绑定切换/撤销：取消在途运行（尽力通知执行方）。"""
        from aichat.modules.runs.models import Run
        from aichat.modules.runs.service import RunsService

        runs_service = RunsService(self.ctx, self.session)
        rows = list(await self.session.scalars(
            select(Run).where(
                Run.agent_account_id == agent_account_id,
                Run.state.in_(("queued", "dispatched", "running", "cancel_requested")),
            )
        ))
        for run in rows:
            if run.state == "queued":
                run.state = "cancelled"
            else:
                run.state = "cancelled"
                attempt = await runs_service.current_attempt(run.id)
                if attempt is not None and attempt.connector_id:
                    await self.ctx.hub.send_to_connector(
                        attempt.connector_id,
                        {"type": "run.cancel", "run_id": run.id, "execution_id": attempt.execution_id,
                         "reason": "binding_revoked"},
                    )
                else:
                    self.ctx.cancel_flags.cancel(run.id)
            await runs_service.emit_run_updated(run)

    # ---- 使用授权 ----

    async def add_grant(self, agent_account_id: str, owner_id: str, human_account_id: str) -> AgentGrant:
        await self.require_owner(agent_account_id, owner_id)
        target = await self.session.get(Account, human_account_id)
        if target is None or target.kind != "human":
            raise validation_failed("授权对象必须是人类账号")
        existing = await self.session.scalar(
            select(AgentGrant).where(AgentGrant.agent_account_id == agent_account_id,
                                     AgentGrant.human_account_id == human_account_id)
        )
        if existing is not None:
            existing.revoked_at = None
            return existing
        grant = AgentGrant(id=new_id(), agent_account_id=agent_account_id, human_account_id=human_account_id)
        self.session.add(grant)
        await self.audit.record("grant.add", "agent", agent_account_id, actor_account_id=owner_id,
                                summary={"human": human_account_id})
        return grant

    async def revoke_grant(self, agent_account_id: str, owner_id: str, human_account_id: str) -> None:
        await self.require_owner(agent_account_id, owner_id)
        grant = await self.session.scalar(
            select(AgentGrant).where(AgentGrant.agent_account_id == agent_account_id,
                                     AgentGrant.human_account_id == human_account_id)
        )
        if grant is None:
            raise not_found("授权不存在")
        grant.revoked_at = utcnow()
        await self.audit.record("grant.revoke", "agent", agent_account_id, actor_account_id=owner_id,
                                summary={"human": human_account_id})

    async def list_grants(self, agent_account_id: str, owner_id: str) -> list[AgentGrant]:
        await self.require_owner(agent_account_id, owner_id)
        rows = await self.session.scalars(
            select(AgentGrant).where(AgentGrant.agent_account_id == agent_account_id)
        )
        return list(rows)

    # ---- 供应商白名单（管理员） ----

    async def upsert_endpoint(self, code: str, display_name: str, base_url: str, protocol: str,
                              enabled: bool, admin_id: str) -> ProviderEndpoint:
        # 白名单限制：禁止私网/本机地址与非常规跳转
        lowered = base_url.lower()
        if lowered.startswith("http://") or any(
            host in lowered for host in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254.", "10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.30.", "172.31.", "metadata")
        ):
            raise validation_failed("端点必须是 HTTPS 且不得指向私网/本机地址")
        row = await self.session.get(ProviderEndpoint, code)
        if row is None:
            row = ProviderEndpoint(code=code, display_name=display_name, base_url=base_url,
                                   protocol=protocol, enabled=enabled)
            self.session.add(row)
        else:
            row.display_name = display_name
            row.base_url = base_url
            row.protocol = protocol
            row.enabled = enabled
        await self.audit.record("provider_endpoint.upsert", "provider_endpoint", code,
                                actor_account_id=admin_id, summary={"base_url": base_url})
        return row
