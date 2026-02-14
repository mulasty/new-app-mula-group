from contextvars import ContextVar
from uuid import UUID

_current_tenant_id: ContextVar[UUID | None] = ContextVar("current_tenant_id", default=None)


def set_current_tenant(tenant_id: UUID | None) -> object:
    return _current_tenant_id.set(tenant_id)


def get_current_tenant() -> UUID | None:
    return _current_tenant_id.get()


def reset_current_tenant(token: object) -> None:
    _current_tenant_id.reset(token)
