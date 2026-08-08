"""
Centralised logging for the HiResToolsGUI application.

Writes both to the in-memory ring buffer (displayed in the GUI) and to
timestamped files under ``~/.hirestoolsgui/logs/``.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Optional


class LogEntry:
    """A single log record kept in the in-memory buffer."""

    __slots__ = ("timestamp", "level", "message")

    def __init__(self, timestamp: str, level: str, message: str) -> None:
        self.timestamp = timestamp
        self.level = level
        self.message = message


class LogManager:
    """
    Application-wide logger with dual output: GUI buffer + file.

    Parameters
    ----------
    max_entries:
        Maximum number of :class:`LogEntry` items kept in the in-memory
        ring buffer.
    log_dir:
        Directory where log files are written.  Created automatically.
    """

    _DEFAULT_LOG_DIR = Path.home() / ".hirestoolsgui" / "logs"

    def __init__(
        self,
        max_entries: int = 5_000,
        log_dir: Optional[Path] = None,
    ) -> None:
        self._buffer: Deque[LogEntry] = deque(maxlen=max_entries)
        self._log_dir = log_dir or self._DEFAULT_LOG_DIR
        self._logger = self._setup_file_logger()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def info(self, message: str) -> None:
        """Log an informational message."""
        self._emit("INFO", message)

    def warning(self, message: str) -> None:
        """Log a warning."""
        self._emit("WARNING", message)

    def error(self, message: str) -> None:
        """Log an error."""
        self._emit("ERROR", message)

    def success(self, message: str) -> None:
        """Log a successful operation."""
        self._emit("SUCCESS", message)

    def entries(self) -> Deque[LogEntry]:
        """Return a reference to the in-memory ring buffer."""
        return self._buffer

    def clear(self) -> None:
        """Purge the in-memory buffer (file logs are preserved)."""
        self._buffer.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit(self, level: str, message: str) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        entry = LogEntry(timestamp, level, message)
        self._buffer.append(entry)

        # Also write to file logger.
        log_method = getattr(self._logger, level.lower(), self._logger.info)
        log_method(message)

    def _setup_file_logger(self) -> logging.Logger:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("dff2dsf_gui")
        logger.setLevel(logging.DEBUG)

        # Avoid duplicate handlers on repeated instantiation.
        if logger.handlers:
            return logger

        filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
        file_path = self._log_dir / filename
        handler = logging.FileHandler(str(file_path), encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger


