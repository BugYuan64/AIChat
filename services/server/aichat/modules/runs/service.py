"""runs 模块：AI 任务的创建、领取（租约+fencing）、执行推进、终态与恢复。

两种执行方式（模型 API / 连接器）在本模块汇合为同一种 Run/Message/事件流；
外部 I/O 一律不在持锁事务内进行。状态机见 contracts/PROTOCOL.md §8。
"""

from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.context import AppContext
from aichat.core.errors import forbidden, not_found, stale_fence, temporarily_unavailable, validation_failed
from aichat.core.ids import new_id
from aichat.core.outbox import emit
from aichat.core.security import sha256_hex, utcnow
from aichat.modules.agents.models import AgentProfile, RuntimeBinding
from aichat.modules.audit.service import AuditService
from aichat.modules.conversations.models import Conversation, MembershipInterval
from aichat.modules.identity.models import Account
from aichat.modules.messages.models import Message
from aichat.modules.messages.service import MessagesService
from aichat.modules.runs.models import Run, RunAttempt, RunContextItem

ACTIVE_RUN_STATES = ("dispatched", "running", "cancel_requested")


def _iso(dt) -> str | None:
    return dt.isoformat() + "Z" if dt is not None else None


class RunsService:
    def __init__(self, ctx: AppContext, session: AsyncSession) -> None:
        self.ctx = ctx
        self.settings = ctx.settings
        self.session = session
        self.messages = MessagesService(ctx, session)
        self.audit = AuditService(session)

    # ---- 触发创建（与消息同事务） ----

    async def create_for_trigger(
        self, conv: Conversation, trigger: Message, agent_account_id: str, requester_account_id: str
    ) -> Run | None:
        agent = await self.session.get(Account, agent_account_id)
        if agent is None or agent.status != "active" or agent.kind != "ai":
            return None
        binding = await self.messages.enabled_binding(agent_account_id)
        if binding is None:
            return None
        if not await self.messages.has_active_grant(agent_account_id, requester_account_id):
            return None
        ai_membership = await self.messages.active_membership(conv.id, agent_account_id)
        if ai_membership is None:
            return None

        queued = await self.session.scalar(
            select(func.count()).select_from(Run).where(
                Run.agent_account_id == agent_account_id, Run.state == "queued"
            )
        )
        if queued and queued >= self.settings.max_agent_queued_runs:
            raise temporarily_unavailable("该 AI 的任务队列已满，请稍后重试")

        now = utcnow()
        run = Run(
            id=new_id(),
            conversation_id=conv.id,
            trigger_message_id=trigger.id,
            agent_account_id=agent_account_id,
            requester_account_id=requester_account_id,
            state="queued",
            is_auto=True,
            binding_generation=binding.generation,
            permission_version=conv.permission_version,
            policy_snapshot={
                "mode": binding.mode,
                "deadline_seconds": self.settings.run_deadline_seconds,
                "max_output_bytes": self.settings.ai_message_max_bytes,
                "context_messages": self.settings.max_context_messages,
            },
            deadline_at=now + timedelta(seconds=self.settings.run_deadline_seconds),
            queue_deadline_at=now + timedelta(seconds=self.settings.run_queue_deadline_seconds),
        )
        self.session.add(run)
        await self.session.flush()

        # 上下文快照：创建时固定，不随后续消息变化；必须包含触发消息
        context_query = (
            select(Message)
            .where(
                Message.conversation_id == conv.id,
                Message.seq >= ai_membership.joined_seq,
                Message.seq <= min(ai_membership.left_seq, trigger.seq)
                if ai_membership.left_seq is not None else Message.seq <= trigger.seq,
            )
            .order_by(Message.seq.desc())
            .limit(self.settings.max_context_messages)
        )
        rows = list(await self.session.scalars(context_query))
        rows.reverse()
        for msg in rows:
            sender = await self.session.get(Account, msg.sender_account_id) if msg.sender_account_id else None
            self.session.add(
                RunContextItem(
                    id=new_id(),
                    run_id=run.id,
                    message_id=msg.id,
                    seq=msg.seq,
                    sender_account_id=msg.sender_account_id,
                    sender_kind=sender.kind if sender is not None else "system",
                    text=msg.text or "",
                )
            )
        await self.emit_run_updated(run)
        return run

    # ---- 事件 ----

    async def emit_run_updated(self, run: Run) -> None:
        await emit(
            self.session,
            "run.updated",
            {
                "run_id": run.id,
                "conversation_id": run.conversation_id,
                "agent_account_id": run.agent_account_id,
                "state": run.state,
                "response_message_id": run.response_message_id,
            },
            conversation_id=run.conversation_id,
        )

    # ---- 领取（worker / 连接器调度） ----

    async def claim_next(self, modes: list[str]) -> tuple[Run, RunAttempt] | None:
        """领取一个到期 queued run；生成新 attempt（execution_id + fencing_token）。
        modes 限定执行方式：API 进程领取 connector（持有 hub），worker 进程领取 model_api。"""
        now = utcnow()
        binding = RuntimeBinding.__table__
        query = (
            select(Run)
            .where(
                Run.state == "queued",
                Run.queue_deadline_at > now,
                Run.agent_account_id.in_(
                    select(binding.c.agent_account_id).where(
                        binding.c.enabled.is_(True), binding.c.mode.in_(modes)
                    )
                ),
                Run.agent_account_id.not_in(
                    select(Run.agent_account_id).where(Run.state.in_(ACTIVE_RUN_STATES))
                ),
            )
            .order_by(Run.created_at.asc())
            .limit(8)
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        candidates = list(await self.session.scalars(query))
        for run in candidates:
            # 每人并发的活动任务上限
            active_for_human = await self.session.scalar(
                select(func.count()).select_from(Run).where(
                    Run.requester_account_id == run.requester_account_id,
                    Run.state.in_(ACTIVE_RUN_STATES),
                )
            )
            if active_for_human and active_for_human >= self.settings.max_human_active_runs:
                continue
            binding_row = await self.session.get(RuntimeBinding, run.agent_account_id)
            if binding_row is None or not binding_row.enabled or binding_row.mode not in modes:
                continue
            if binding_row.mode == "connector":
                if binding_row.connector_id is None or not self.ctx.hub.connector_online(binding_row.connector_id):
                    continue
            run.attempt_count += 1
            run.fencing_counter += 1
            run.state = "dispatched"
            attempt = RunAttempt(
                id=new_id(),
                run_id=run.id,
                attempt_no=run.attempt_count,
                execution_id=new_id() + "-" + str(run.attempt_count),
                mode=binding_row.mode,
                connector_id=binding_row.connector_id if binding_row.mode == "connector" else None,
                fencing_token=run.fencing_counter,
                lease_until=now + timedelta(seconds=self.settings.run_lease_seconds),
            )
            self.session.add(attempt)
            await self.session.flush()
            return run, attempt
        return None

    async def build_offer(self, run: Run, attempt: RunAttempt) -> dict:
        """构造派发帧。

        三样东西必须随帧下发，否则连接器侧只能靠猜：
        - system_prompt：连接器模式下 RuntimeBinding 由配对创建、不带它，
          此前适配器永远拿到 None，系统提示词在连接器模式静默失效。
        - deadline_at：与 policy 里的 deadline_seconds 一并给出，避免两端
          对超时的认知不一致。
        - permission_mode / workspace_dir：CLI 的执行权限由平台下发，
          不能让适配器用自己进程环境的默认值（那会是 CLI 自身的 yolo）。
        """
        from aichat.modules.agents.models import AgentProfile, RuntimeBinding

        binding = await self.session.get(RuntimeBinding, run.agent_account_id)
        agent_policy = await self.session.get(AgentProfile, run.agent_account_id)
        return {
            "type": "run.offer",
            "event_id": new_id(),
            "occurred_at": _iso(utcnow()),
            "protocol_version": 1,
            "run_id": run.id,
            "execution_id": attempt.execution_id,
            "attempt_no": attempt.attempt_no,
            "fencing_token": attempt.fencing_token,
            "binding_generation": run.binding_generation,
            "lease_until": _iso(attempt.lease_until),
            "deadline_at": _iso(run.deadline_at),
            "agent_id": run.agent_account_id,
            "conversation_id": run.conversation_id,
            "trigger_message_id": run.trigger_message_id,
            "system_prompt": binding.system_prompt if binding is not None else None,
            "execution_policy": {
                "permission_mode": agent_policy.permission_mode if agent_policy is not None else "plan",
                "workspace_dir": agent_policy.workspace_dir if agent_policy is not None else None,
            },
            "policy": run.policy_snapshot,
        }

    async def context_items(self, run_id: str) -> list[RunContextItem]:
        rows = await self.session.scalars(
            select(RunContextItem).where(RunContextItem.run_id == run_id).order_by(RunContextItem.seq.asc())
        )
        return list(rows)

    # ---- 执行推进（连接器帧 / 模型 worker 共用；均需验证当前 attempt） ----

    async def _verify_attempt(self, run_id: str, execution_id: str, attempt_no: int, fencing_token: int,
                              *, must_be_running: bool = False) -> tuple[Run, RunAttempt]:
        run = await self.session.get(Run, run_id)
        if run is None:
            raise not_found("任务不存在")
        # Keep writes in protocol lock order and refresh after acquiring the lock.
        await self.messages.get_conversation(run.conversation_id, lock=True)
        query = select(Run).where(Run.id == run_id).execution_options(populate_existing=True)
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        run = await self.session.scalar(query)
        if run.state not in ACTIVE_RUN_STATES:
            raise stale_fence("任务已结束")
        attempt = await self.session.scalar(
            select(RunAttempt).where(RunAttempt.run_id == run_id, RunAttempt.attempt_no == attempt_no)
        )
        if attempt is None or attempt.execution_id != execution_id:
            raise stale_fence("execution 不匹配")
        if attempt.fencing_token != fencing_token or run.fencing_counter != fencing_token:
            raise stale_fence()
        if attempt.state not in ("leased", "running"):
            raise stale_fence("执行已结束")
        if must_be_running and attempt.state != "running":
            raise stale_fence("执行不在 running 状态")
        return run, attempt

    async def get_attempt_by_execution(self, execution_id: str) -> RunAttempt | None:
        return await self.session.scalar(select(RunAttempt).where(RunAttempt.execution_id == execution_id))

    async def current_attempt(self, run_id: str) -> RunAttempt | None:
        return await self.session.scalar(
            select(RunAttempt).where(RunAttempt.run_id == run_id,
                                     RunAttempt.state.in_(("leased", "running")))
        )

    async def ack(self, run_id: str, execution_id: str, attempt_no: int, fencing_token: int) -> tuple[Run, RunAttempt]:
        """连接器 run.accepted：确认接收并续租。仅确认接收，不等于执行许可。"""
        run, attempt = await self._verify_attempt(run_id, execution_id, attempt_no, fencing_token)
        if attempt.state != "leased":
            raise stale_fence("attempt 状态不允许 ack")
        attempt.acked_at = utcnow()
        attempt.lease_until = utcnow() + timedelta(seconds=self.settings.run_lease_seconds)
        return run, attempt

    async def renew_lease(self, attempt: RunAttempt) -> None:
        """运行期心跳续租（仅执行所有权，与连接活性心跳分离）。"""
        attempt.lease_until = utcnow() + timedelta(seconds=self.settings.run_lease_seconds)

    async def start(self, run_id: str, execution_id: str, attempt_no: int, fencing_token: int) -> tuple[Run, RunAttempt, Message]:
        run, attempt = await self._verify_attempt(run_id, execution_id, attempt_no, fencing_token)
        if attempt.state != "leased":
            raise stale_fence("attempt 状态不允许 start")
        conv = await self.messages.get_conversation(run.conversation_id, lock=True)
        if conv.permission_version != run.permission_version or conv.status != "active":
            raise stale_fence("会话权限已变化，任务失效")
        if attempt.lease_until <= utcnow():
            raise stale_fence("租约已过期")
        run.deadline_at = utcnow() + timedelta(seconds=self.settings.run_deadline_seconds)
        message = await self.messages.create_run_response_message(conv, run, run.agent_account_id)
        run.response_message_id = message.id
        run.state = "running"
        attempt.state = "running"
        attempt.started_at = utcnow()
        await self.emit_run_updated(run)
        return run, attempt, message

    async def apply_delta(
        self, run_id: str, execution_id: str, attempt_no: int, fencing_token: int,
        chunk_index: int, text: str, *, chunk_hash: str | None = None,
        force_event: bool | None = None, batch: bool = False,
    ) -> dict:
        run, attempt = await self._verify_attempt(run_id, execution_id, attempt_no, fencing_token,
                                                  must_be_running=True)
        if run.state == "cancel_requested":
            raise stale_fence("任务已请求取消")
        message = await self.session.get(Message, run.response_message_id)
        if message is None:
            raise stale_fence("回复消息不存在")
        if len(message.text or "") + len(text) > self.settings.ai_message_max_bytes:
            await self._fail_locked(run, attempt, "output_too_large", "输出超过上限", "none")
            raise validation_failed("输出超过上限")
        # 连续性：重复片（同内容）幂等；缺片报 DELTA_GAP（batch 模式用于服务端
        # 模型执行器的合并落库，序号由执行器自身保证连续，允许跳读中间序号）
        if chunk_index <= attempt.last_chunk_index:
            if chunk_index == attempt.last_chunk_index and chunk_hash is not None and attempt.last_chunk_hash == chunk_hash:
                return {"duplicate": True}
            raise stale_fence("过期的增量序号")
        if chunk_index != attempt.last_chunk_index + 1 and not batch:
            from aichat.core.errors import delta_gap

            raise delta_gap(attempt.last_chunk_index + 1)
        now = utcnow()
        if force_event is None:
            force_event = (
                attempt.last_event_at is None
                or (now - attempt.last_event_at).total_seconds() * 1000 >= self.settings.delta_checkpoint_min_interval_ms
                or len(message.text or "") + len(text) - (attempt.pending_bytes or 0) >= self.settings.delta_checkpoint_pending_bytes
            )
        await self.messages.append_run_delta(message, chunk_index, text, force_event=force_event)
        attempt.last_chunk_index = chunk_index
        attempt.last_chunk_hash = chunk_hash
        if force_event:
            attempt.last_event_at = now
            attempt.pending_bytes = 0
        else:
            attempt.pending_bytes = (attempt.pending_bytes or 0) + len(text.encode("utf-8"))
        return {"checkpointed": force_event}

    async def complete(
        self, run_id: str, execution_id: str, attempt_no: int, fencing_token: int,
        final_text: str | None, content_hash: str | None, last_chunk_index: int, usage: dict | None,
        finish_reason: str | None,
    ) -> tuple[Run, RunAttempt]:
        run, attempt = await self._verify_attempt(run_id, execution_id, attempt_no, fencing_token,
                                                  must_be_running=True)
        if attempt.last_chunk_index != last_chunk_index:
            raise validation_failed("last_chunk_index 与已接收增量不一致")
        message = await self.session.get(Message, run.response_message_id)
        if content_hash is not None:
            if sha256_hex(message.text or "") != content_hash:
                raise validation_failed("final_content_hash 校验失败")
            final = message.text or ""
        else:
            final = final_text if final_text is not None else (message.text or "")
        if len(final.encode("utf-8")) > self.settings.ai_message_max_bytes:
            raise validation_failed("最终输出超过上限")
        await self.messages.finalize_run_message(message, final)
        attempt.state = "succeeded"
        attempt.finished_at = utcnow()
        run.state = "succeeded"
        await self.emit_run_updated(run)
        await self.audit.record("run.succeed", "run", run.id,
                                summary={"execution_id": execution_id, "usage": usage or {}})
        return run, attempt

    async def fail(self, run_id: str, execution_id: str, attempt_no: int, fencing_token: int,
                   error_code: str, message: str, side_effect: str = "none") -> tuple[Run, RunAttempt]:
        run, attempt = await self._verify_attempt(run_id, execution_id, attempt_no, fencing_token)
        return await self._fail_locked(run, attempt, error_code, message, side_effect)

    async def _fail_locked(self, run: Run, attempt: RunAttempt, error_code: str, message: str,
                           side_effect: str) -> tuple[Run, RunAttempt]:
        attempt.state = "failed"
        attempt.finished_at = utcnow()
        run.state = "recovery_required" if side_effect == "unknown" else "failed"
        response = await self.session.get(Message, run.response_message_id) if run.response_message_id else None
        if response is not None:
            await self.messages.mark_run_message_terminal(response, "unknown" if side_effect == "unknown" else "error")
        await self.emit_run_updated(run)
        await self.audit.record("run.fail", "run", run.id,
                                summary={"error_code": error_code, "side_effect": side_effect})
        return run, attempt

    # ---- 取消 ----

    async def request_cancel(self, run_id: str, actor_account_id: str | None = None) -> Run:
        run = await self.session.get(Run, run_id)
        if run is None:
            raise not_found("任务不存在")
        if run.state == "queued":
            run.state = "cancelled"
            await self.emit_run_updated(run)
            return run
        if run.state in ("dispatched", "running", "cancel_requested"):
            if run.state != "cancel_requested":
                run.state = "cancel_requested"
                await self.emit_run_updated(run)
            await self._notify_executor_cancel(run)
            return run
        return run

    async def _notify_executor_cancel(self, run: Run) -> None:
        attempt = await self.session.scalar(
            select(RunAttempt).where(RunAttempt.run_id == run.id, RunAttempt.state == "running")
        )
        if attempt is None:
            return
        if attempt.mode == "connector" and attempt.connector_id:
            await self.ctx.hub.send_to_connector(
                attempt.connector_id,
                {"type": "run.cancel", "run_id": run.id, "execution_id": attempt.execution_id, "reason": "user"},
            )
        else:
            self.ctx.cancel_flags.cancel(run.id)

    async def confirm_cancelled(self, execution_id: str, side_effect: str = "none") -> Run:
        attempt = await self.get_attempt_by_execution(execution_id)
        if attempt is None:
            raise not_found("执行不存在")
        run = await self.session.get(Run, attempt.run_id)
        if run.state in ("cancelled", "succeeded", "failed", "expired", "recovery_required"):
            return run
        attempt.state = "cancelled"
        attempt.finished_at = utcnow()
        run.state = "recovery_required" if side_effect == "unknown" else "cancelled"
        if run.response_message_id:
            response = await self.session.get(Message, run.response_message_id)
            if response is not None:
                await self.messages.mark_run_message_terminal(response, "unknown" if side_effect == "unknown" else "cancel")
        await self.emit_run_updated(run)
        await self.audit.record("run.cancel", "run", run.id, summary={"execution_id": execution_id})
        return run

    # ---- 重试 ----

    async def retry(self, run_id: str, actor_account_id: str, *, is_admin: bool = False) -> Run:
        run = await self.session.get(Run, run_id)
        if run is None:
            raise not_found("任务不存在")
        profile = await self.session.get(AgentProfile, run.agent_account_id)
        is_owner = profile is not None and profile.owner_account_id == actor_account_id
        if run.requester_account_id != actor_account_id and not is_owner and not is_admin:
            raise forbidden("只有触发者或 AI 所有者可以重试")
        if not await self.messages.has_active_grant(run.agent_account_id, run.requester_account_id):
            raise forbidden("原触发者的 AI 使用授权已失效")
        trigger = await self.session.get(Message, run.trigger_message_id)
        conv = await self.messages.get_conversation(run.conversation_id, lock=True)
        new_run = Run(
            id=new_id(),
            conversation_id=run.conversation_id,
            trigger_message_id=run.trigger_message_id,
            agent_account_id=run.agent_account_id,
            requester_account_id=run.requester_account_id,
            state="queued",
            is_auto=False,
            retried_from_run_id=run.id,
            binding_generation=run.binding_generation,
            permission_version=conv.permission_version,
            policy_snapshot=run.policy_snapshot,
            deadline_at=utcnow() + timedelta(seconds=self.settings.run_deadline_seconds),
            queue_deadline_at=utcnow() + timedelta(seconds=self.settings.run_queue_deadline_seconds),
        )
        self.session.add(new_run)
        await self.session.flush()
        for item in await self.context_items(run.id):
            self.session.add(
                RunContextItem(
                    id=new_id(), run_id=new_run.id, message_id=item.message_id, seq=item.seq,
                    sender_account_id=item.sender_account_id, sender_kind=item.sender_kind,
                    text=item.text, truncated=item.truncated,
                )
            )
        await self.emit_run_updated(new_run)
        await self.audit.record("run.retry", "run", new_run.id, actor_account_id=actor_account_id,
                                summary={"from_run": run.id})
        return new_run

    # ---- 维护循环（worker / API 进程） ----

    async def expire_stale_runs(self) -> int:
        """过期清理与租约回收。返回处理条数。"""
        now = utcnow()
        changed = 0
        # 排队超时 → expired
        rows = list(await self.session.scalars(
            select(Run).where(Run.state == "queued", Run.queue_deadline_at <= now).limit(50)
        ))
        for run in rows:
            run.state = "expired"
            await self.emit_run_updated(run)
            changed += 1
        # 派发租约超时（未开始）→ 回收重派或失败
        rows = list((await self.session.execute(
            select(Run, RunAttempt).join(RunAttempt, RunAttempt.run_id == Run.id)
            .where(Run.state == "dispatched", RunAttempt.state == "leased",
                   or_(RunAttempt.lease_until <= now, Run.deadline_at <= now)).limit(50)
        )).all())
        for run, attempt in rows:
            attempt.state = "expired"
            attempt.finished_at = now
            run.fencing_counter += 1
            run.state = "failed" if run.attempt_count >= self.settings.run_max_attempts else "queued"
            await self.emit_run_updated(run)
            changed += 1
        # 运行租约超时 → recovery_required（结果未知）
        rows = list((await self.session.execute(
            select(Run, RunAttempt).outerjoin(
                RunAttempt, (RunAttempt.run_id == Run.id)
                & RunAttempt.state.in_(("leased", "running"))
            ).where(Run.state.in_(("running", "cancel_requested")),
                    or_(RunAttempt.lease_until <= now,
                        Run.deadline_at <= now - timedelta(seconds=15))).limit(50)
        )).all())
        for run, attempt in rows:
            if attempt is not None:
                # 连接器侧的 CLI 进程可能还在跑。服务端已经认定失败，
                # 必须显式要求它停下来，否则会在主机上留下孤儿进程。
                if attempt.mode == "connector" and attempt.connector_id:
                    await self.ctx.hub.send_to_connector(
                        attempt.connector_id,
                        {"type": "run.cancel", "run_id": run.id,
                         "execution_id": attempt.execution_id, "reason": "deadline_exceeded"},
                    )
                attempt.state = "expired"
                attempt.finished_at = now
            run.state = "recovery_required" if run.state == "running" else "cancelled"
            if run.response_message_id:
                response = await self.session.get(Message, run.response_message_id)
                if response is not None:
                    await self.messages.mark_run_message_terminal(
                        response, "unknown" if run.state == "recovery_required" else "cancel"
                    )
            await self.emit_run_updated(run)
            changed += 1
        return changed

    # ---- 读取 ----

    async def get_run_for_human(self, run_id: str, account_id: str) -> Run:
        run = await self.session.get(Run, run_id)
        if run is None:
            raise not_found("任务不存在")
        membership = await self.session.scalar(
            select(MembershipInterval).where(
                MembershipInterval.conversation_id == run.conversation_id,
                MembershipInterval.account_id == account_id,
                MembershipInterval.left_at.is_(None),
            )
        )
        trigger = await self.session.get(Message, run.trigger_message_id)
        visible_member = (membership is not None and trigger is not None
                          and trigger.seq >= membership.joined_seq)
        profile = await self.session.get(AgentProfile, run.agent_account_id)
        is_owner = profile is not None and profile.owner_account_id == account_id
        allowed = visible_member or is_owner or run.requester_account_id == account_id
        if not allowed:
            raise forbidden("无权查看该任务")
        return run

    def run_out(self, run: Run) -> dict:
        return {
            "run_id": run.id,
            "conversation_id": run.conversation_id,
            "trigger_message_id": run.trigger_message_id,
            "agent_account_id": run.agent_account_id,
            "requester_account_id": run.requester_account_id,
            "response_message_id": run.response_message_id,
            "state": run.state,
            "retried_from_run_id": run.retried_from_run_id,
            "attempt_count": run.attempt_count,
            "deadline_at": _iso(run.deadline_at),
            "created_at": _iso(run.created_at),
            "updated_at": _iso(run.updated_at),
        }
