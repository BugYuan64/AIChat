"""worker：模型 API 任务的执行编排（领取→start→流式 delta→终态）。

每一步用独立短事务提交；外部 HTTP 调用不持锁。取消经 ctx.cancel_flags。
"""

import asyncio
import contextlib
import logging

from sqlalchemy import select

from aichat.core.context import AppContext
from aichat.core.security import sha256_hex
from aichat.modules.agents.models import ProviderCredential, ProviderEndpoint, RuntimeBinding
from aichat.modules.runs.models import Run, RunAttempt, RunContextItem
from aichat.modules.runs.service import RunsService
from aichat.runtime.base import ModelCallSpec, ProviderError
from aichat.runtime.model_api import stream_chat

logger = logging.getLogger("aichat.worker")


async def _load_spec(ctx: AppContext, run_id: str) -> ModelCallSpec:
    async with ctx.db.session_factory() as session:
        run = await session.get(Run, run_id)
        binding = await session.get(RuntimeBinding, run.agent_account_id)
        if binding is None:
            raise RuntimeError("binding missing")
        endpoint = await session.get(ProviderEndpoint, binding.provider_code)
        credential = await session.get(ProviderCredential, binding.credential_id)
        if endpoint is None or credential is None:
            raise RuntimeError("provider config missing")
        items = await session.scalars(
            select(RunContextItem).where(RunContextItem.run_id == run_id).order_by(RunContextItem.seq.asc())
        )
        return ModelCallSpec(
            base_url=endpoint.base_url,
            api_key=ctx.cipher.decrypt(credential.ciphertext),
            model=binding.model_name or "",
            system_prompt=binding.system_prompt,
            context=[{"sender_kind": i.sender_kind, "text": i.text} for i in items],
            timeout_seconds=ctx.settings.model_http_timeout_seconds,
        )


async def execute_model_run(ctx: AppContext, run_id: str) -> None:
    """完整执行一个 model_api run；run 已终态则直接返回。"""
    cancel_event = ctx.cancel_flags.register(run_id)
    full_text: list[str] = []
    lease_task = None
    lease_lost = False
    try:
        async with ctx.db.session_factory() as session:
            runs = RunsService(ctx, session)
            run = await session.get(Run, run_id)
            if run is None or run.state not in ("dispatched", "running"):
                return
            attempt = await runs.current_attempt(run_id)
            if attempt is None:
                return
            await runs.start(run_id, attempt.execution_id, attempt.attempt_no, attempt.fencing_token)
            await session.commit()
            execution_id, attempt_no, fencing = attempt.execution_id, attempt.attempt_no, attempt.fencing_token

        async def renew_ownership() -> None:
            nonlocal lease_lost
            interval = min(ctx.settings.run_lease_renew_seconds, ctx.settings.run_lease_seconds / 3)
            try:
                while True:
                    await asyncio.sleep(interval)
                    async with ctx.db.session_factory() as session:
                        runs = RunsService(ctx, session)
                        _, current = await runs._verify_attempt(run_id, execution_id, attempt_no, fencing)
                        await runs.renew_lease(current)
                        await session.commit()
            except Exception:
                logger.warning("模型任务续租停止 run=%s", run_id, exc_info=True)
                lease_lost = True
                cancel_event.set()

        lease_task = asyncio.create_task(renew_ownership())
        spec = await _load_spec(ctx, run_id)
        chunk_index = -1
        buffer: list[str] = []
        buffer_bytes = 0
        last_flush = asyncio.get_event_loop().time()

        async def flush(force_event: bool) -> None:
            nonlocal buffer, buffer_bytes, last_flush
            if not buffer:
                return
            text = "".join(buffer)
            async with ctx.db.session_factory() as session:
                runs = RunsService(ctx, session)
                await runs.apply_delta(run_id, execution_id, attempt_no, fencing,
                                       chunk_index, text, force_event=force_event, batch=True)
                await session.commit()
            buffer, buffer_bytes = [], 0
            last_flush = asyncio.get_event_loop().time()

        try:
            async for text in stream_chat(spec):
                if cancel_event.is_set():
                    break
                chunk_index += 1
                buffer.append(text)
                full_text.append(text)
                buffer_bytes += len(text.encode("utf-8"))
                if asyncio.get_event_loop().time() - last_flush >= 1.0 or buffer_bytes >= ctx.settings.delta_checkpoint_pending_bytes:
                    await flush(force_event=True)
            # A cancel forbids further delta writes. Discard the pending buffer
            # before confirming it instead of turning STALE_FENCE into failure.
            if not cancel_event.is_set():
                await flush(force_event=False)

            async with ctx.db.session_factory() as session:
                runs = RunsService(ctx, session)
                if cancel_event.is_set():
                    if lease_lost:
                        # Expiry maintenance owns the unknown outcome; a storage
                        # or ownership failure is not a user cancellation.
                        return
                    await runs.confirm_cancelled(execution_id, "none")
                    await session.commit()
                    return
                aggregated = "".join(full_text)
                if len(aggregated.encode("utf-8")) <= ctx.settings.final_text_inline_max_bytes:
                    await runs.complete(run_id, execution_id, attempt_no, fencing,
                                        final_text=aggregated, content_hash=None,
                                        last_chunk_index=chunk_index, usage=None, finish_reason="stop")
                else:
                    await runs.complete(run_id, execution_id, attempt_no, fencing,
                                        final_text=None, content_hash=sha256_hex(aggregated),
                                        last_chunk_index=chunk_index, usage=None, finish_reason="stop")
                await session.commit()
        except ProviderError as exc:
            async with ctx.db.session_factory() as session:
                runs = RunsService(ctx, session)
                await runs.fail(run_id, execution_id, attempt_no, fencing,
                                exc.code, "模型调用失败", "none")
                await session.commit()
    except Exception:
        logger.exception("model run 执行异常 run=%s", run_id)
        try:
            async with ctx.db.session_factory() as session:
                runs = RunsService(ctx, session)
                attempt = await runs.current_attempt(run_id)
                if attempt is not None:
                    await runs.fail(run_id, attempt.execution_id, attempt.attempt_no, attempt.fencing_token,
                                    "internal_error", "内部执行错误", "none")
                    await session.commit()
        except Exception:
            logger.exception("model run 失败落库也异常 run=%s", run_id)
    finally:
        if lease_task is not None:
            lease_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lease_task
        ctx.cancel_flags.unregister(run_id)
