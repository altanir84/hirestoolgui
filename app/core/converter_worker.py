"""
Sequential converter that invokes ``dff2dsf`` via :class:`subprocess.run`
inside a single :class:`QThread`.

No :class:`QProcess`, no parallelism — one file at a time, maximum
reliability.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, List, NamedTuple, Optional

from PySide6.QtCore import QObject, Signal, Slot


class ConversionTask(NamedTuple):
    """Description of a single file to convert."""
    source: Path
    destination: Path


class ConverterWorker(QObject):
    """
    Runs ``dff2dsf`` sequentially inside a dedicated thread.

    Signals
    -------
    task_started(source, dest):
        Emitted immediately before launching ``dff2dsf``.
    task_finished(source, dest, exit_code, error_output):
        Emitted after the process completes.
    task_skipped(source, reason):
        Emitted when a task is skipped (e.g. collision rename).
    all_done():
        Emitted after the last task has been processed or cancelled.
    """

    task_started = Signal(str, str)
    task_finished = Signal(str, str, int, str)
    task_skipped = Signal(str, str)
    all_done = Signal()

    def __init__(
        self,
        binary: str,
        tasks: List[ConversionTask],
        cancel_event,  # threading.Event
        overwrite: bool = False,
    ) -> None:
        super().__init__()
        self._binary = binary
        self._tasks = tasks
        self._cancel = cancel_event
        self._overwrite = overwrite

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    @Slot()
    def run(self) -> None:
        """Process every task sequentially and emit ``all_done``."""
        for task in self._tasks:
            if self._cancel.is_set():
                break

            source_str = str(task.source)
            dest = task.destination

            # Ensure output directory exists.
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Handle destination collision.
            final_dest = dest
            skip_reason = ""
            if final_dest.exists():
                if self._overwrite:
                    final_dest.unlink()
                else:
                    final_dest = self._find_available_name(final_dest)
                    skip_reason = (
                        f"Renamed to avoid collision: {final_dest.name}"
                    )
                    self.task_skipped.emit(source_str, skip_reason)

            dest_str = str(final_dest)
            self.task_started.emit(source_str, dest_str)

            try:
                proc = subprocess.run(
                    [self._binary, source_str, dest_str],
                    capture_output=True,
                    timeout=300,
                    text=True,
                )
                exit_code = proc.returncode
                stderr = proc.stderr.strip()
            except subprocess.TimeoutExpired:
                exit_code = -1
                stderr = "TIMEOUT"
            except Exception as exc:
                exit_code = -2
                stderr = str(exc)

            self.task_finished.emit(source_str, dest_str, exit_code, stderr)

        self.all_done.emit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_available_name(original: Path) -> Path:
        """Generate a non-colliding filename by appending ``_1``, ``_2``, …"""
        stem = original.stem
        suffix = original.suffix
        parent = original.parent
        counter = 1
        while True:
            candidate = parent / f"{stem}_{counter},{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1



