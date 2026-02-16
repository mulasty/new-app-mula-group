import json
import logging
from datetime import UTC, datetime

from app.infrastructure.logging.context import get_request_id, get_tenant_id


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "request_id": get_request_id(),
            "tenant_id": get_tenant_id(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
