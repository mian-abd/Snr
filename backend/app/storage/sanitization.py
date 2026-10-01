from __future__ import annotations

import re
from collections.abc import Iterable

_ACCOUNT_FIELD = re.compile(
    r'(?i)(["\']?(?:user_id|account_id)["\']?\s*[:=]\s*["\']?)([^"\',}\s]+)'
)
_AUTHORIZATION = re.compile(
    r'(?i)(["\']?authorization["\']?\s*[:=]\s*["\']?)(?:bearer\s+)?([^"\',}\s]+)'
)
_API_KEY_FIELD = re.compile(
    r'(?i)(["\']?(?:api[_-]?key|token)["\']?\s*[:=]\s*["\']?)([^"\',}\s]+)'
)
_WINDOWS_PATH = re.compile(r"(?i)\b[A-Z]:\\(?:[^\\\s\"']+\\)*[^\\\s\"']+")


def sanitize_text(value: str, *, secrets: Iterable[str] = ()) -> str:
    """Remove credentials, account identifiers, and machine-specific paths from text."""

    sanitized = value
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, "[redacted]")
    sanitized = _ACCOUNT_FIELD.sub(r"\1[redacted]", sanitized)
    sanitized = _AUTHORIZATION.sub(r"\1[redacted]", sanitized)
    sanitized = _API_KEY_FIELD.sub(r"\1[redacted]", sanitized)
    return _WINDOWS_PATH.sub("[local-path]", sanitized)
