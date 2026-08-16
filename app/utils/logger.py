"""
Centralised logging for HiResToolsGUI.

Writes both to the in-memory ring buffer (displayed in the GUI) and to
timestamped files under ``~/.HiResToolsGUI/logs/``.

Also provides :class:`ErrorLogManager` for per-conversion error logs
that only persist to disk when non-successful events occur.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, List, Optional


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

    _DEFAULT_LOG_DIR = Path.home() / ".HiResToolsGUI" / "logs"

    def __init__(
        self,
        max_entries: int = 5_000,
        log_dir: Optional[Path] = None,
    ) -> None:
        self._buffer: Deque[LogEntry] = deque(maxlen=max_entries)
        self._log_dir = log_dir or self._DEFAULT_LOG_DIR
        self._current_log_file: Optional[Path] = None
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

    def log_file_path(self) -> Optional[Path]:
        """Return the path to the current log file."""
        return self._current_log_file


    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = LogEntry(timestamp, level, message)
        self._buffer.append(entry)

        log_method = getattr(self._logger, level.lower(), self._logger.info)
        log_method(message)

    def _setup_file_logger(self) -> logging.Logger:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("HiResToolsGUI")
        logger.setLevel(logging.DEBUG)

        if logger.handlers:
            return logger

        filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
        file_path = self._log_dir / filename
        self._current_log_file = file_path
        handler = logging.FileHandler(str(file_path), encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger


class ErrorLogManager:
    """
    Per-conversion error log that only persists to disk when files are
    not processed (failures or skipped).

    Only entries for non-successful events are recorded.  If any such
    event occurs, the entire buffer is flushed to a timestamped file
    under the log directory.  Otherwise it is discarded.
    """

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        self._log_dir = log_dir or Path.home() / ".HiResToolsGUI" / "logs"
        self._buffer: List[LogEntry] = []
        self._has_entries = False
        self._file_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_failure(
        self,
        source: str,
        file_type: str,
        exit_code: int,
        stderr: str = "",
    ) -> None:
        """
        Record a conversion failure.

        Parameters
        ----------
        source:
            Absolute path to the source file.
        file_type:
            ``"DFF"`` or ``"ISO"``.
        exit_code:
            Process exit code.
        stderr:
            Standard error output from the converter, if any.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"FAILED [{file_type}] {source} (exit={exit_code})"
        self._buffer.append(LogEntry(timestamp, "ERROR", msg))
        if stderr:
            self._buffer.append(
                LogEntry(timestamp, "ERROR", f"  stderr: {stderr}")
            )
        self._has_entries = True

    def add_skipped(
        self,
        source: str,
        file_type: str,
        reason: str,
    ) -> None:
        """
        Record a file that was skipped (not processed).

        Parameters
        ----------
        source:
            Absolute path to the source file.
        file_type:
            ``"DFF"`` or ``"ISO"``.
        reason:
            Human-readable explanation (e.g. path validation, collision,
            invalid folder structure).
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"SKIPPED [{file_type}] {source} — {reason}"
        self._buffer.append(LogEntry(timestamp, "WARNING", msg))
        self._has_entries = True

    def finalise(self) -> Optional[Path]:
        """
        Write the buffer to disk if any entries were recorded.

        Returns the path to the error log file, or ``None`` if no
        non-successful events occurred.
        """
        if not self._has_entries:
            self._buffer.clear()
            return None

        self._log_dir.mkdir(parents=True, exist_ok=True)
        filename = datetime.now().strftime("%Y%m%d_%H%M%S") + "_errors.log"
        self._file_path = self._log_dir / filename

        with open(self._file_path, "w", encoding="utf-8") as fh:
            fh.write("HiResToolsGUI — Error Log\n")
            fh.write("=" * 60 + "\n\n")
            for i, entry in enumerate(self._buffer):
                if i > 0:
                    fh.write("-" * 60 + "\n")
                fh.write(
                    f"[{entry.timestamp}] [{entry.level}] {entry.message}\n"
                )

        self._buffer.clear()
        self._has_entries = False
        return self._file_path

    def reset(self) -> None:
        """Discard the current buffer without writing."""
        self._buffer.clear()
        self._has_entries = False
        self._file_path = None







