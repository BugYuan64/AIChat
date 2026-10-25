"""后台循环：outbox 扇出、run 派发（连接器 offer / 模型执行）、过期维护。

扇出只在持有 hub 的进程运行（v1 单实例约束，见 PROTOCOL.md §0/§5）；
模型执行经 execute_model_run 在任意进程执行。
"""

import asyncio
import logging

from aichat.core.context import AppContext
from aichat.modules.realtime.service import RealtimeService
from aichat.modules.runs.service import RunsService
from aichat.worker.executor import execute_model_run

logger = logging.getLogger("aichat.worker")

_model_tasks: set[asyncio.Task] = set()


async def fanout_loop(ctx: AppContext) -> None:
    while True:
        notified: list[str] = []
        handled = False
        try:
            async with ctx.db.session_factory() as session:
                service = RealtimeService(ctx, session)
                notified, handled = await service.fanout_one()
                await session.commit()
        except Exception:
            logger.exception("fanout 异常")
        if handled and notified:
            await ctx.hub.notify_accounts(notified)
        if not handled:
            await asyncio.sleep(ctx.settings.fanout_poll_seconds)


async def dispatch_loop(ctx: AppContext) -> None:
    while True:
        dispatched = False
        try:
            async with ctx.db.session_factory() as session:
                runs = RunsService(ctx, session)
                claimed = await runs.claim_next(["model_api", "connector"])
                if claimed is not None:
                    run, attempt = claimed
                    offer: dict | None = None
                    connector_id = None
                    if attempt.mode == "connector":
                        connector_id = attempt.connector_id
                        offer = runs.build_offer(run, attempt)
                        offer["context"] = [
                            {
                                "seq": item.seq,
                                "sender_account_id": item.sender_account_id,
                                "sender_kind": item.sender_kind,
                                "text": item.text,
                                "truncated": item.truncated,
                            }
                            for item in await runs.context_items(run.id)
                        ]
                    run_id = run.id
                    await session.commit()
                    if attempt.mode == "model_api":
                        task = asyncio.create_task(execute_model_run(ctx, run_id))
                        _model_tasks.add(task)
                        task.add_done_callback(_model_tasks.discard)
                    elif connector_id and offer is not None:
                        # 事务外发送 offer；送达失败由租约回收路径兜底
                        ok = await ctx.hub.send_to_connector(connector_id, offer)
                        if not ok:
                            logger.warning("run.offer 发送失败（连接器离线）run=%s", run_id)
                    dispatched = True
        except Exception:
            logger.exception("dispatch 异常")
        if not dispatched:
            await asyncio.sleep(ctx.settings.run_loop_seconds)


async def maintenance_loop(ctx: AppContext) -> None:
    while True:
        try:
            async with ctx.db.session_factory() as session:
                runs = RunsService(ctx, session)
                changed = await runs.expire_stale_runs()
                await session.commit()
                if changed:
                    await ctx.hub.notify_accounts([])
        except Exception:
            logger.exception("maintenance 异常")
        await asyncio.sleep(2.0)


ALL_LOOPS = (fanout_loop, dispatch_loop, maintenance_loop)
