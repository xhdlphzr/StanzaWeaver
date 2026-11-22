# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

"""Application logging (logging + RotatingFileHandler).

- File output: ~/.stanza_weaver/logs/stanza.log, rotated by RotatingFileHandler:
  once a log file reaches max_bytes it rotates, keeping backup_count backups
  (stanza.log.1, stanza.log.2 ...); the oldest backups beyond that count are
  overwritten, i.e. "new logs overwrite the oldest ones once the quota is
  reached, keeping a fixed number of backups".
- Console output: kept as well (visible when the desktop app starts).
- Each module gets a named logger via get_logger(__name__); the log directory
  can be overridden with the STANZAWEAVER_LOG_DIR environment variable.
"""

import logging
import logging.handlers
import os
from pathlib import Path

DEFAULT_DIR = Path.home() / ".stanza_weaver" / "logs"
DEFAULT_FILENAME = "stanza.log"
DEFAULT_MAX_BYTES = 1 * 1024 * 1024  # Max size of a single log file: 1 MiB
DEFAULT_BACKUP_COUNT = 5  # Number of rotated backups to keep

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False


def get_logs_dir() -> Path:
    """Return the log directory (overridable via STANZAWEAVER_LOG_DIR).

    Returns:
        Log directory path.

    """
    env = os.environ.get("STANZAWEAVER_LOG_DIR")
    if env:
        return Path(env)
    return DEFAULT_DIR


def setup_logging(
    logs_dir: Path | None = None,
    level: int = logging.INFO,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    """Configure the global logging system (idempotent; first call wins).

    Mount both a RotatingFileHandler and a console StreamHandler on the root
    logger; each module's named logger propagates to both.

    Args:
        logs_dir: Log directory (defaults to get_logs_dir()).
        level: Log level.
        max_bytes: Max size of a single log file (rotation is triggered on reaching it).
        backup_count: Number of rotated backups to keep (older ones are overwritten).

    Returns:
        The application's root logger (named "stanzaweaver").

    """
    global _configured
    if _configured:
        return logging.getLogger("stanzaweaver")
    _configured = True

    logs_dir = logs_dir or get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / DEFAULT_FILENAME

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    app_logger = logging.getLogger("stanzaweaver")
    app_logger.debug(
        "Logging system initialized: %s (max_bytes=%s, backup_count=%s)",
        log_file,
        max_bytes,
        backup_count,
    )
    return app_logger


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (organized by module name).

    Args:
        name: Logger name; conventionally __name__.

    Returns:
        A logging.Logger instance.

    """
    return logging.getLogger(name)
