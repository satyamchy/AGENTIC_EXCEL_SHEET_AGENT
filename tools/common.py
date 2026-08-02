"""
Shared utilities: structured logging + retry-with-backoff decorator.
Every tool uses @retry so transient failures can recover instead of
crashing the whole agent run.
"""
import functools
import logging
import sys
import time

from config import LOG_DIR, LOG_LEVEL, MAX_TOOL_RETRIES

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "agent.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def retry(max_attempts: int = MAX_TOOL_RETRIES, delay_seconds: float = 1.5):
    """Retry a tool function on exception or success=False."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            log = get_logger(func.__module__)
            last_error = None
            for attempt in range(1, max_attempts + 2):
                try:
                    result = func(*args, **kwargs)
                    if isinstance(result, dict) and not result.get("success", True):
                        last_error = result.get("error", "unknown error")
                        if result.get("retryable") is False:
                            return result
                        if attempt <= max_attempts:
                            log.warning(
                                "%s failed (attempt %d/%d): %s; retrying in %.1fs",
                                func.__name__,
                                attempt,
                                max_attempts + 1,
                                last_error,
                                delay_seconds,
                            )
                            time.sleep(delay_seconds)
                            continue
                    return result
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    log.warning(
                        "%s raised on attempt %d/%d: %s",
                        func.__name__,
                        attempt,
                        max_attempts + 1,
                        exc,
                    )
                    if attempt <= max_attempts:
                        time.sleep(delay_seconds)
                        continue
                    return {"success": False, "error": last_error, "step": func.__name__}
            return {"success": False, "error": last_error, "step": func.__name__}

        return wrapper

    return decorator


def progress(message: str):
    """Emit a user-visible progress line, also logged."""
    print(f"  -> {message}", flush=True)
    get_logger("agent.progress").info(message)
