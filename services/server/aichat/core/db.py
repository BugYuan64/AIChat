from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from aichat.core.config import Settings


class Base(DeclarativeBase):
    pass


class Database:
    """引擎与会话工厂容器。app 启动时构造一次。"""

    def __init__(self, settings: Settings):
        self.engine: AsyncEngine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_all(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：请求级会话，成功提交、异常回滚。"""
    db: Database = request.app.state.ctx.db
    async with db.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
