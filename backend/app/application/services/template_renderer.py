import re
from typing import Any

TEMPLATE_VAR_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_.-]+)\s*}}")


def _resolve_path(payload: dict[str, Any], path: str) -> str:
    current: Any = payload
    for token in path.split("."):
        if isinstance(current, dict) and token in current:
            current = current[token]
        else:
            return ""
    if current is None:
        return ""
    return str(current)


def render_prompt_template(template: str, variables: dict[str, Any]) -> str:
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return _resolve_path(variables, key)

    return TEMPLATE_VAR_PATTERN.sub(_replace, template)
