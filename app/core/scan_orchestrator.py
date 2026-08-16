"""
Scan orchestrator for HiResToolsGUI.

Manages the lifecycle of background folder scans: worker threads,
cancellation, and progress signals.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, List, Optional, Set

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.core.file_scanner import FileScanner
from app.models.file_node import FileNode


class _ScanWorker(QThread):
    """
    Background worker that runs :meth:`FileScanner.scan` in a separate
    thread so the UI remains responsive during scanning.
    """

    scan_finished = Signal(object)

    def __init__(
        self,
        scanner: FileScanner,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._scanner = scanner

    def run(self) -> None:
        """Execute the scan and emit the result."""
        root_node = self._scanner.scan()
        self.scan_finished.emit(root_node)


class ScanOrchestrator(QObject):
    """
    Orchestrates background folder scanning.

    Signals
    -------
    scan_started():
        Emitted when a scan begins.
    scan_finished(new_root):
        Emitted when a scan completes, carrying the resulting
        :class:`FileNode` tree.
    scan_cancelled():
        Emitted when a scan is cancelled.
    """

    scan_started = Signal()
    scan_finished = Signal(object)
    scan_cancelled = Signal()

    def __init__(
        self,
        warning_callback: Optional[Callable[[str], None]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._warning = warning_callback or (lambda _: None)
        self._cancel_event: Optional[threading.Event] = None
        self._scan_worker: Optional[_ScanWorker] = None
        self._scanning = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_scanning(self) -> bool:
        """Return ``True`` when a background scan is in progress."""
        return self._scanning

    def cancel(self) -> None:
        """Request cancellation of the running background scan."""
        if self._cancel_event is not None:
            self._cancel_event.set()

    def start_scan(
        self,
        folders: List[Path],
        progress_callback: Optional[Callable[[Path], None]] = None,
        exclude_folders: Optional[Set[Path]] = None,
    ) -> None:
        """
        Launch a background scan for *folders*.

        If a scan is already running, it is cancelled first.
        """
        if self._scanning:
            self._cancel_and_wait()

        self._scanning = True
        self._cancel_event = threading.Event()

        scanner = FileScanner(
            folders,
            warning_callback=self._warning,
            progress_callback=progress_callback,
            cancel_event=self._cancel_event,
            exclude_folders=exclude_folders,
        )

        self._scan_worker = _ScanWorker(scanner, self)
        self._scan_worker.scan_finished.connect(self._on_scan_done)
        self._scan_worker.finished.connect(self._cleanup_worker)
        self._scan_worker.start()

        self.scan_started.emit()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _cancel_and_wait(self) -> None:
        """Cancel the running scan and wait for the worker to stop."""
        if self._cancel_event is not None:
            self._cancel_event.set()

        if (
            self._scan_worker is not None
            and self._scan_worker.isRunning()
        ):
            self._scan_worker.quit()
            self._scan_worker.wait(5000)

        self._scanning = False
        self._cancel_event = None
        self._scan_worker = None

    @Slot()
    def _cleanup_worker(self) -> None:
        """Release the finished worker thread."""
        self._scan_worker = None

    @Slot(object)
    def _on_scan_done(self, new_root: FileNode) -> None:
        """Handle scan completion."""
        was_cancelled = (
            self._cancel_event is not None
            and self._cancel_event.is_set()
        )

        self._scanning = False
        self._cancel_event = None

        if was_cancelled:
            self.scan_cancelled.emit()
        self.scan_finished.emit(new_root)



