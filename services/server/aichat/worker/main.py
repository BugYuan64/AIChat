"""独立 worker 进程入口：python -m aichat.worker [--no-model]。

扇出与维护在此运行；模型任务执行也在此运行（v1 单实例约束下，
连接器 offer 派发依赖 hub 连接，仍由 API 进程承担；本进程派发仅限 model_api）。
"""

import argparse
import asyncio
import logging

from aichat.core.config import get_settings
from aichat.core.context import AppContext, CancelFlags
from aichat.core.db import Database
from aichat.core.security import CredentialCipher
from aichat.modules.realtime.hub import RealtimeHub
from aichat.worker import loops as loops_mod


def build_context() -> AppContext:
    settings = get_settings()
    return AppContext(
        settings=settings,
        db=Database(settings),
        hub=RealtimeHub(),
        cipher=CredentialCipher(settings),
        cancel_flags=CancelFlags(),
    )


async def main(no_model: bool) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ctx = build_context()
    await ctx.db.create_all()
    tasks = []
    for loop in loops_mod.ALL_LOOPS:
        if no_model and loop is loops_mod.dispatch_loop:
            continue
        tasks.append(asyncio.create_task(loop(ctx)))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="aichat-worker")
    parser.add_argument("--no-model", action="store_true", help="不执行模型任务（仅扇出与维护）")
    args = parser.parse_args()
    asyncio.run(main(args.no_model))
