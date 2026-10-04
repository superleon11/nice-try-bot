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
    return int(env_float(name, default))
