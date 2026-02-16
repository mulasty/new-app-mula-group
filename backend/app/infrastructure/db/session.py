from collections.abc import Generator
from time import perf_counter

from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.infrastructure.observability.metrics import observe_db_query

engine = create_engine(settings.sqlalchemy_database_uri, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("query_started_at_stack", []).append(perf_counter())


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    stack = conn.info.get("query_started_at_stack", [])
    if not stack:
        return
    started_at = stack.pop(-1)
    observe_db_query(perf_counter() - started_at, operation="sync_sql")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
