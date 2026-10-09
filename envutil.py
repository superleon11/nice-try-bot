"""Small helpers for reading numbers from environment variables."""

import logging
import os

log = logging.getLogger(__name__)


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        log.warning("%s=%r is not a number, using %s", name, raw, default)
        return default


def env_int(name: str, default: int) -> int:
    # Parse as an integer first: going through float would corrupt Discord IDs (18-19 digits).
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return int(env_float(name, default))


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")
