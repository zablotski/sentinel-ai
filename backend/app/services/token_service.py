import json
from typing import Any

import tiktoken

_ENCODER = tiktoken.get_encoding("cl100k_base")


def count_string_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_ENCODER.encode(text))


def count_package_context_tokens(package: dict[str, Any]) -> int:
    try:
        payload = json.dumps(package, default=str)
    except (TypeError, ValueError):
        payload = str(package)
    return count_string_tokens(payload)
