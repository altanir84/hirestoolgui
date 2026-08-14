"""
Conversion orchestrator for HiResToolsGUI.

Manages the full lifecycle of a conversion batch: task execution,
worker-thread management, progress polling, and UI finalisation.
"""

from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from app.core.converter_worker import ConversionTask, ConverterWorker
from app.core.post_processor import PostProcessor
from app.core.tag_preserver import TagPreserver
from app.utils.logger import ErrorLogManager, LogManager
from app.widgets.progress_panel import ProgressPanel


class ConversionOrchestrator(QObject):
    """
    Orchestrates a single conversion batch.

    Parameters
    ----------
    log_manager:
        Application-wide log manager.
    error_log:
        Per-batch error log.
    tag_preserver:
        ID3 tag cache.
    progress_panel:
        UI panel for progress bars and log display.
    binary_dff2dsf:
        Path to the ``dff2dsf`` binary.
    binary_sacd_extract:
        Path to the ``sacd_extract`` binary.
    sacd_stereo:
        ``True`` for stereo extraction.
    sacd_multichannel:
        ``True`` for multi-channel extraction.
    sacd_cue:
        ``True`` for CUE sheet export.
    sacd_output_format:
        CLI flag for SACD output format.
    overwrite:
        ``True`` to overwrite existing destination files.

    Signals
    -------
    started():
        Emitted when the batch begins.
    task_started(source, dest):
        Emitted for each task that begins.
    task_finished(source, dest, exit_code, stderr):
        Emitted for each task that completes.
    task_skipped(source, reason):
        Emitted for each task that is skipped.
    finished(success_count, failed_count, total_count):
        Emitted when the entire batch completes.
    """

    started = Signal()
    task_started = Signal(str, str)
    task_finished = Signal(str, str, int, str)
    task_skipped = Signal(str, str)
    finished = Signal(int, int, int)

    def __init__(
        self,
        log_manager: LogManager,
        error_log: ErrorLogManager,
        tag_preserver: TagPreserver,
        progress_panel: ProgressPanel,
        binary_dff2dsf: str,
        binary_sacd_extract: str,
        sacd_stereo: bool = True,
        sacd_multichannel: bool = False,
        sacd_cue: bool = False,
        sacd_output_format: str = "-s",
        overwrite: bool = False,
        keep_folder: bool = False,


    ) -> None:
        super().__init__()
        self._log_manager = log_manager
        self._error_log = error_log
        self._tag_preserver = tag_preserver
        self._progress_panel = progress_panel
        self._binary_dff2dsf = binary_dff2dsf
        self._binary_sacd_extract = binary_sacd_extract
        self._sacd_stereo = sacd_stereo
        self._sacd_multichannel = sacd_multichannel
        self._sacd_cue = sacd_cue
        self._sacd_output_format = sacd_output_format
        self._overwrite = overwrite
        self._keep_folder = keep_folder

        self._cancel_event = threading.Event()
        self._threads: List[QThread] = []
        self._workers: List[ConverterWorker] = []
        self._task_map: Dict[str, str] = {}
        self._announced_albums: set = set()
        self._completed_tasks = 0
        self._success_count = 0
        self._failed_count = 0
        self._total_tasks = 0

        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._poll_progress)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, tasks: List[ConversionTask]) -> None:
        """
        Begin processing *tasks* in a background thread.

        The caller must have already populated the tag cache and
        obtained user confirmation via dialogs.
        """
        self._task_map = {str(t.source): t.converter for t in tasks}
        self._announced_albums.clear()
        self._completed_tasks = 0
        self._success_count = 0
        self._failed_count = 0
        self._total_tasks = len(tasks)
        self._cancel_event.clear()

        self._progress_panel.reset()
        self._progress_panel.set_overall_progress(0, self._total_tasks)
        self._error_log.reset()

        self._log_manager.info(
            f"Starting conversion of {len(tasks)} file(s)"
        )

        thread = QThread()
        worker = ConverterWorker(
            self._binary_dff2dsf,
            self._binary_sacd_extract,
            tasks,
            sacd_stereo=self._sacd_stereo,
            sacd_multichannel=self._sacd_multichannel,
            sacd_cue=self._sacd_cue,
            sacd_output_format=self._sacd_output_format,
            cancel_event=self._cancel_event,
            overwrite=self._overwrite,
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.task_started.connect(self._on_task_started)
        worker.task_finished.connect(self._on_task_finished)
        worker.task_skipped.connect(self._on_task_skipped)
        worker.all_done.connect(self._on_worker_done)
        thread.finished.connect(
            lambda t=thread: self._on_thread_finished(t)
        )

        self._threads.append(thread)
        self._workers.append(worker)

        self.started.emit()
        self._progress_timer.start(200)
        thread.start()

    def cancel(self) -> None:
        """Request graceful cancellation of the running batch."""
        self._cancel_event.set()
        self._log_manager.warning(
            "Cancellation requested — finishing current file..."
        )

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    @Slot(str, str)
    def _on_task_started(self, source: str, dest: str) -> None:
        source_path = Path(source)
        converter_type = self._task_map.get(source, "")

        if not converter_type:
            converter_type = (
                "sacd_extract"
                if source_path.suffix.lower() == ".iso"
                else "dff2dsf"
            )

        if converter_type == "dff2dsf":
            album_dir = str(source_path.parent)
            if album_dir not in self._announced_albums:
                self._announced_albums.add(album_dir)
                self._log_manager.info(
                    f"Album: {source_path.parent.name}"
                )
                self._progress_panel.append_log(
                    self._log_manager.entries()[-1]
                )

        self._log_manager.info(f"Converting: {source_path.name}")
        self._progress_panel.append_log(self._log_manager.entries()[-1])
        self.task_started.emit(source, dest)

    @Slot(str, str, int, str)
    def _on_task_finished(
        self, source: str, dest: str, exit_code: int, stderr: str
    ) -> None:
        self._completed_tasks += 1
        self._progress_panel.set_overall_progress(
            self._completed_tasks, self._total_tasks
        )

        converter_type = self._task_map.get(source, "")

        if exit_code == 0:
            self._success_count += 1
            self._log_manager.success(f"OK: {Path(source).name}")

            if converter_type == "dff2dsf":
                applied = self._tag_preserver.apply_tags(
                    Path(source), Path(dest)
                )
                if not applied:
                    self._log_manager.warning(
                        f"Could not preserve tags for: {Path(source).name}"
                    )
                PostProcessor.process_dff_output(Path(dest))

            if converter_type == "sacd_extract":
                dest_path = Path(dest)
                dest_dir = dest_path.parent

                # sacd_extract creates a subfolder named after the ISO
                # inside dest_dir.  Move everything up, then remove it.
                if not self._keep_folder:
                    for subdir in dest_dir.iterdir():
                        if subdir.is_dir():
                            for f in subdir.iterdir():
                                shutil.move(
                                    str(f), str(dest_dir / f.name)
                                )
                            subdir.rmdir()
                            break

                # Handle channel sub-folders created by sacd_extract.
                # Stereo only: move contents up, remove folder.
                # Multichannel only: move contents up, add -mch suffix
                # to .dsf files and update CUE references.
                channel_dirs = [
                    d for d in dest_dir.iterdir()
                    if d.is_dir()
                    and d.name.lower() in (
                        "stereo", "[stereo]", "6ch", "multi", "[multi]",
                    )
                ]
                for channel_dir in channel_dirs:
                    suffix = (
                        "-mch"
                        if self._sacd_multichannel
                        and not self._sacd_stereo
                        else ""
                    )
                    for f in channel_dir.iterdir():
                        dest_name = f.name
                        if suffix and f.suffix.lower() == ".dsf":
                            dest_name = f.stem + suffix + f.suffix
                        shutil.move(
                            str(f), str(dest_dir / dest_name)
                        )
                    channel_dir.rmdir()

                PostProcessor.process_sacd_output(dest_dir)
        else:
            self._failed_count += 1
            self._log_manager.error(
                f"FAILED: {Path(source).name} (exit={exit_code})"
            )
            if stderr and exit_code != 0:
                self._log_manager.error(f"  stderr: {stderr}")

            file_type = (
                "ISO" if converter_type == "sacd_extract" else "DFF"
            )
            self._error_log.add_failure(
                source, file_type, exit_code, stderr
            )

        self._progress_panel.append_log(self._log_manager.entries()[-1])
        self.task_finished.emit(source, dest, exit_code, stderr)

    @Slot(str, str)
    def _on_task_skipped(self, source: str, reason: str) -> None:
        self._log_manager.warning(
            f"SKIPPED: {Path(source).name} — {reason}"
        )
        self._progress_panel.append_log(self._log_manager.entries()[-1])
        file_type = "ISO" if source.lower().endswith(".iso") else "DFF"
        self._error_log.add_skipped(source, file_type, reason)
        self.task_skipped.emit(source, reason)

    @Slot()
    def _on_worker_done(self) -> None:
        """Finalise when the worker signals completion."""
        self._progress_timer.stop()
        self._workers.clear()
        self._tag_preserver.clear()

        self._progress_panel.conversion_finished()

        self._log_manager.info("All conversions completed.")
        self._log_manager.info(
            f"Summary: {self._success_count} succeeded, "
            f"{self._failed_count} failed, "
            f"{self._total_tasks} total"
        )
        log_path = self._log_manager.log_file_path()
        if log_path is not None:
            self._log_manager.info(f"Log file: {log_path}")

        error_log_path = self._error_log.finalise()
        if error_log_path is not None:
            self._log_manager.info(f"Error log: {error_log_path}")

        entries = self._log_manager.entries()
        extra = 1 if error_log_path is not None else 0
        for i in range(1, 4 + extra):
            self._progress_panel.append_log(entries[-i])

        self.finished.emit(
            self._success_count, self._failed_count, self._total_tasks
        )

    def _on_thread_finished(self, thread: QThread) -> None:
        """Remove a finished thread from the active list."""
        if thread in self._threads:
            self._threads.remove(thread)

    @Slot()
    def _poll_progress(self) -> None:
        """Poll the worker's progress queue and update the UI."""
        for worker in self._workers:
            while True:
                item = worker.get_progress()
                if item is None:
                    break
                current, total, message = item

                if current == 0 and total == 0:
                    self._log_manager.info(message)
                    self._progress_panel.append_log(
                        self._log_manager.entries()[-1]
                    )
                else:
                    self._progress_panel.set_file_progress(
                        current, total
                    )
                    match = re.search(
                        r"Processing\s+\[(.+)\]", message
                    )
                    if match:
                        track_name = Path(match.group(1)).name
                        self._log_manager.info(
                            f"  Track {current}/{total}: {track_name}"
                        )
                        self._progress_panel.append_log(
                            self._log_manager.entries()[-1]
                        )



