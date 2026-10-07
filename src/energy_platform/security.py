"""Remove credentials before any API response is stored."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE = {
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "client_secret",
    "password",
}


def clean_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"https", "http"}:
        return value
    query = [
        (k, "[REDACTED]" if k.lower() in SENSITIVE else v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
    ]
    # User information is never retained in source URLs.
    netloc = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), ""))


def sanitize(value):
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if k.lower() in SENSITIVE else sanitize(v))
            for k, v in value.items()
            if k != "request"
        }
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        return re.sub(r"https?://[^\s\"<>]+", lambda m: clean_url(m.group(0)), value)
    return value
