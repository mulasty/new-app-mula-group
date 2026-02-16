from contextvars import ContextVar

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
_tenant_id_ctx: ContextVar[str | None] = ContextVar("tenant_id", default=None)


def set_request_id(request_id: str | None) -> object:
    return _request_id_ctx.set(request_id)


def get_request_id() -> str | None:
    return _request_id_ctx.get()


def reset_request_id(token: object) -> None:
    _request_id_ctx.reset(token)


def set_tenant_id(tenant_id: str | None) -> object:
    return _tenant_id_ctx.set(tenant_id)


def get_tenant_id() -> str | None:
    return _tenant_id_ctx.get()


def reset_tenant_id(token: object) -> None:
    _tenant_id_ctx.reset(token)
