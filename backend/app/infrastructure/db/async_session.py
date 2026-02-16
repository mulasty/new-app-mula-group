from collections.abc import AsyncGenerator
from time import perf_counter

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.infrastructure.observability.metrics import observe_db_query

async_engine = create_async_engine(settings.sqlalchemy_database_uri, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, expire_on_commit=False, autoflush=False)


@event.listens_for(async_engine.sync_engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("query_started_at_stack", []).append(perf_counter())


@event.listens_for(async_engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    stack = conn.info.get("query_started_at_stack", [])
    if not stack:
        return
    started_at = stack.pop(-1)
    observe_db_query(perf_counter() - started_at, operation="async_sql")


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as db:
        yield db
