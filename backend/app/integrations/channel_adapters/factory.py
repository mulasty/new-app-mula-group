import importlib
import logging
import pkgutil
from types import ModuleType
from typing import Iterable

from sqlalchemy.orm import Session

from app.domain.models.channel import Channel
from app.domain.models.post import Post
from app.integrations.channel_adapters.base_adapter import AdapterResolutionError, BaseChannelAdapter

logger = logging.getLogger(__name__)

_DISCOVERED = False
_ADAPTER_REGISTRY: dict[str, type[BaseChannelAdapter]] = {}
_SKIP_MODULES = {"base_adapter", "factory"}


class MissingChannelAdapter(BaseChannelAdapter):
    channel_type = "missing"
    is_fallback = True

    def __init__(self, requested_channel_type: str) -> None:
        self.requested_channel_type = requested_channel_type

    @classmethod
    def get_capabilities(cls) -> dict:
        return {}

    async def validate_credentials(self) -> None:
        raise AdapterResolutionError(f"No adapter registered for channel type '{self.requested_channel_type}'")

    async def publish_text(self, *, post: Post, channel: Channel) -> dict:
        raise AdapterResolutionError(f"No adapter registered for channel type '{self.requested_channel_type}'")

    async def publish_media(self, *, post: Post, channel: Channel) -> dict:
        raise AdapterResolutionError(f"No adapter registered for channel type '{self.requested_channel_type}'")

    async def refresh_credentials(self) -> None:
        raise AdapterResolutionError(f"No adapter registered for channel type '{self.requested_channel_type}'")


def _iter_subclasses(root: type[BaseChannelAdapter]) -> Iterable[type[BaseChannelAdapter]]:
    for subclass in root.__subclasses__():
        yield subclass
        yield from _iter_subclasses(subclass)


def _discover_adapter_modules() -> None:
    package = importlib.import_module("app.integrations.channel_adapters")
    if not isinstance(package, ModuleType) or not hasattr(package, "__path__"):
        return

    for module_info in pkgutil.iter_modules(package.__path__, prefix="app.integrations.channel_adapters."):
        module_name = module_info.name.rsplit(".", 1)[-1]
        if module_name in _SKIP_MODULES:
            continue
        try:
            importlib.import_module(module_info.name)
        except Exception as exc:
            logger.warning(
                "channel_adapter_module_skip module=%s reason=%s",
                module_info.name,
                exc,
            )


def _load_registry() -> dict[str, type[BaseChannelAdapter]]:
    global _DISCOVERED
    if _DISCOVERED and _ADAPTER_REGISTRY:
        return _ADAPTER_REGISTRY

    _discover_adapter_modules()
    discovered: dict[str, type[BaseChannelAdapter]] = {}
    for adapter_cls in _iter_subclasses(BaseChannelAdapter):
        if getattr(adapter_cls, "is_fallback", False):
            continue
        channel_type = (getattr(adapter_cls, "channel_type", "") or "").strip().lower()
        if not channel_type:
            continue
        discovered[channel_type] = adapter_cls

    _ADAPTER_REGISTRY.clear()
    _ADAPTER_REGISTRY.update(discovered)
    _DISCOVERED = True
    logger.info(
        "channel_adapter_registry_loaded total=%s types=%s",
        len(_ADAPTER_REGISTRY),
        ",".join(sorted(_ADAPTER_REGISTRY.keys())),
    )
    return _ADAPTER_REGISTRY


def list_registered_adapter_types() -> list[str]:
    registry = _load_registry()
    return sorted(registry.keys())


def get_adapter_capabilities(channel_type: str) -> dict:
    normalized_type = channel_type.strip().lower()
    registry = _load_registry()
    adapter_cls = registry.get(normalized_type)
    if adapter_cls is None:
        raise AdapterResolutionError(f"Unsupported channel adapter: {normalized_type}")
    return adapter_cls.get_capabilities()


def get_channel_adapter(channel_type: str, db: Session, *, strict: bool = True) -> BaseChannelAdapter:
    normalized_type = channel_type.strip().lower()
    registry = _load_registry()
    adapter_cls = registry.get(normalized_type)
    if adapter_cls is None:
        logger.error(
            "channel_adapter_resolution_failed channel_type=%s available_types=%s",
            normalized_type,
            ",".join(sorted(registry.keys())),
        )
        if strict:
            raise AdapterResolutionError(f"Unsupported channel adapter: {normalized_type}")
        return MissingChannelAdapter(normalized_type)

    logger.info(
        "channel_adapter_resolved channel_type=%s adapter=%s",
        normalized_type,
        adapter_cls.__name__,
    )
    return adapter_cls(db)
