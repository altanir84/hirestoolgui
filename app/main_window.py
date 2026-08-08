
"""
Main application window for the DFF2DSF GUI.

Wires together the config panel, file tree, output panel, and progress
panel.  Manages the conversion lifecycle — validation, task building,
worker-thread orchestration, and cancellation.

Layout
------
The window uses a vertical :class:`QSplitter` so the user can
drag-resize the boundary between the file-tree area (upper) and the
progress/log area (lower).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QFileDialog
)

from app.core.converter_worker import ConversionTask, ConverterWorker
from app.core.path_validator import PathValidator
from app.utils.logger import LogManager
from app.widgets.config_panel import ConfigPanel
from app.widgets.file_panel import FilePanel
from app.widgets.output_panel import OutputPanel
from app.widgets.progress_panel import ProgressPanel


class MainWindow(QMainWindow):
    """
    Top-level window of the DFF2DSF GUI application.

    ┌──────────────────────────────────────────┐
    │  ConfigPanel  (binary, workers)          │
    ├──────────────────────────────────────────┤
    │  FilePanel          │  OutputPanel       │
    │  (tree + buttons)   │  (mode selection)  │
    │                     │                    │
    ├─────────────────────┴────────────────────┤  ← draggable splitter
    │  [Start Conversion]                      │
    │  ProgressPanel  (bars + log)             │
    └──────────────────────────────────────────┘
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DFF2DSF Converter")
        self.setMinimumSize(900, 650)

        # Shared mutable state (non-Qt).
        self._log_manager = LogManager()
        self._cancel_event = threading.Event()
        self._threads: List[QThread] = []
        self._workers: List[ConverterWorker] = []
        self._running = False
        
        self._build_ui()
        self._connect_signals()
        self._update_start_button()

        self._pending_workers = 0
        self._completed_tasks = 0
        self._total_tasks = 0
        self._success_count = 0
        self._failed_count = 0

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Assemble the widget tree and set up the vertical splitter."""
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(4, 4, 4, 4)

        # -- Config panel (fixed height at top) --
        self._config_panel = ConfigPanel()
        root_layout.addWidget(self._config_panel)

        # -- Vertical splitter: upper (tree + output) | lower (start + log) --
        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.setChildrenCollapsible(False)

        # Upper widget -------------------------------------------------
        upper = QWidget()
        upper_layout = QHBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)

        self._file_panel = FilePanel()
        self._file_panel.set_warning_callback(self._log_manager.warning)
        self._output_panel = OutputPanel()

        upper_layout.addWidget(self._file_panel, 3)
        upper_layout.addWidget(self._output_panel, 1)

        # Lower widget -------------------------------------------------
        lower = QWidget()
        lower_layout = QVBoxLayout(lower)
        lower_layout.setContentsMargins(0, 0, 0, 0)

        self._btn_start = QPushButton("Start Conversion")
        self._btn_start.setMinimumHeight(40)
        self._btn_start.setStyleSheet(
            "QPushButton { font-size: 14px; font-weight: bold; }"
        )

        self._progress_panel = ProgressPanel(self._log_manager)

        lower_layout.addWidget(self._btn_start)
        lower_layout.addWidget(self._progress_panel, 1)

        # Populate splitter --------------------------------------------
        self._splitter.addWidget(upper)
        self._splitter.addWidget(lower)
        self._splitter.setStretchFactor(0, 3)   # 75 % to tree area
        self._splitter.setStretchFactor(1, 1)   # 25 % to progress area

        root_layout.addWidget(self._splitter, 1)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """Connect all child-widget signals to MainWindow slots."""
        self._config_panel.binary_changed.connect(self._on_binary_changed)
        self._output_panel.mode_changed.connect(self._on_mode_changed)
        self._file_panel.scan_completed.connect(self._update_start_button)
        self._file_panel.selection_changed.connect(self._update_start_button)
        self._btn_start.clicked.connect(self._on_start)
        self._progress_panel.cancel_requested.connect(self._on_cancel)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_binary(self) -> bool:
        """
        Return ``True`` when the configured binary exists and is
        executable on the current system.
        """
        path = self._config_panel.binary_path()
        if path is None:
            self._config_panel.set_binary_status(
                False, "No binary path configured."
            )
            return False
        if not path.is_file():
            self._config_panel.set_binary_status(
                False, f"File not found: {path}"
            )
            return False
        if not os.access(str(path), os.X_OK):
            self._config_panel.set_binary_status(
                False, f"Not executable: {path}"
            )
            return False
        self._config_panel.set_binary_status(
            True, f"Binary found: {path}"
        )
        return True

    def _validate_output(self) -> bool:
        """
        Return ``True`` when the output configuration is valid.

        For single-root mode the target directory is created eagerly
        so that a missing folder does not block the Start button.
        Per-folder mode is always considered valid (the worker creates
        ``converted/`` on the fly next to each source file).
        """
        mode = self._output_panel.output_mode()
        if mode == OutputPanel.MODE_SINGLE:
            root = self._output_panel.output_root()
            if root is None:
                return False
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError:
                return False
        return True

    def _can_start(self) -> bool:
        """``True`` when every pre-condition for conversion is satisfied."""
        if self._running:
            return False
        if not self._validate_binary():
            return False
        if not self._file_panel.has_files():
            return False
        if len(self._file_panel.checked_files()) == 0:
            return False
        if not self._validate_output():
            return False
        return True

    # ------------------------------------------------------------------
    # Slots – UI state updates
    # ------------------------------------------------------------------

    @Slot(Path)
    def _on_binary_changed(self, _path: Path) -> None:
        self._validate_binary()
        self._update_start_button()

    @Slot(str, object)
    def _on_mode_changed(self, _mode: str, _root: Optional[Path]) -> None:
        self._update_start_button()

    @Slot()
    def _update_start_button(self, _unused: int = 0) -> None:
        """Enable or disable the Start button based on current state."""
        self._btn_start.setEnabled(self._can_start())

    # ------------------------------------------------------------------
    # Slots – conversion lifecycle
    # ------------------------------------------------------------------

    @Slot()
    def _on_start(self) -> None:
        """Validate inputs, build tasks, and spawn a single worker thread."""
        # -- Final validation --
        if not self._validate_binary():
            QMessageBox.warning(
                self,
                "Invalid Binary",
                "The dff2dsf binary path is invalid.  "
                "Please configure it in the Converter Configuration panel.",
            )
            return

        if not self._validate_output():
            QMessageBox.warning(
                self,
                "Invalid Output",
                "Please specify a valid output root directory.",
            )
            return

        checked = self._file_panel.checked_files()
        valid, rejected = PathValidator.filter_batch(checked)

        if rejected:
            for rp, reason in rejected:
                self._log_manager.warning(f"Skipping {rp.name}: {reason}")

        if not self._warn_rejected_files(rejected, len(valid)):
            return

        if not valid:
            QMessageBox.information(
                self,
                "Nothing to Convert",
                "No valid DFF files are selected for conversion.",
            )
            return

        # -- Build conversion tasks --
        mode = self._output_panel.output_mode()
        output_root = self._output_panel.output_root()
        tasks = self._build_tasks(valid, mode, output_root)

        # Deal with file collisions
        tasks, overwrite = self._handle_destination_collisions(tasks)
        if not tasks:
            return

        if not tasks:
            QMessageBox.information(
                self,
                "Nothing to Convert",
                "All selected files were skipped during task building.",
            )
            return

        # get confirmation from user
        if not self._confirm_conversion(tasks):
            return

        self._log_manager.info(
            f"Starting conversion of {len(tasks)} file(s) "
            f"(mode={mode})"
        )

        # -- Reset UI for a new run --
        self._running = True
        self._cancel_event.clear()
        self._btn_start.setEnabled(False)
        self._file_panel.setEnabled(False)
        self._output_panel.setEnabled(False)
        self._config_panel.setEnabled(False)
        self._completed_tasks = 0
        self._success_count = 0
        self._failed_count = 0
        self._total_tasks = len(tasks)
        self._progress_panel.reset()
        self._progress_panel.set_overall_progress(0, self._total_tasks)
        self._pending_workers = 1

        # -- Single worker thread --
        thread = QThread()
        worker = ConverterWorker(
            str(self._config_panel.binary_path()),
            tasks,
            self._cancel_event,
            overwrite,
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.task_started.connect(self._on_task_started)
        worker.task_finished.connect(self._on_task_finished)
        worker.task_skipped.connect(self._on_task_skipped)
        worker.all_done.connect(self._on_worker_done)
        # worker.all_done.connect(thread.quit)
        # worker.all_done.connect(self._on_worker_done)
        thread.finished.connect(lambda t=thread: self._on_thread_finished(t))

        self._threads.append(thread)
        self._workers.append(worker)
        
        thread.start()


    @Slot()
    def _on_cancel(self) -> None:
        """Request graceful cancellation of all running workers."""
        self._cancel_event.set()
        self._log_manager.warning(
            "Cancellation requested — finishing current files..."
        )
        self._progress_panel._btn_cancel.setEnabled(False)

    @Slot(str, str)
    def _on_task_started(self, source: str, dest: str) -> None:
        self._log_manager.info(f"Converting: dff2dsf {source} {dest}")
        self._progress_panel.append_log(
            self._log_manager.entries()[-1]
        )

    @Slot(str, str, int, str)
    def _on_task_finished(
        self, source: str, dest: str, exit_code: int, stderr: str
    ) -> None:

        self._completed_tasks += 1
        self._progress_panel.set_overall_progress(
            self._completed_tasks, self._total_tasks
            )

        if exit_code == 0:
            self._success_count += 1
            self._log_manager.success(f"OK: {Path(source).name}")
        else:
            self._failed_count += 1
            self._log_manager.error(
                f"FAILED: {Path(source).name} (exit={exit_code})"
            )
            if stderr:
                self._log_manager.error(f"  stderr: {stderr}")

        self._progress_panel.append_log(
            self._log_manager.entries()[-1]
            )

    @Slot(str, str)
    def _on_task_skipped(self, source: str, reason: str) -> None:
        self._log_manager.warning(
            f"SKIPPED: {Path(source).name} — {reason}"
        )
        self._progress_panel.append_log(
            self._log_manager.entries()[-1]
        )

    def _on_worker_done(self) -> None:
        """Check whether all workers have finished; clean up if so."""
        self._running = False
        self._workers.clear()
        
        # self._threads.clear()
        self._progress_panel.conversion_finished()
        self._log_manager.info("All conversions completed.")
        self._log_manager.info(
            f'Summary: {self._success_count} succeded, '
            f'{self._failed_count} failed, '
            f'{self._total_tasks} total.'
        )
        self._log_manager.info(
            f'Log file: {self._log_manager._log_dir}'
        )
        # Push summary entries to visible log
        entries = self._log_manager.entries()
        for i in range(1, 4):
            self._progress_panel.append_log(entries[-i])

        self._file_panel.setEnabled(True)
        self._output_panel.setEnabled(True)
        self._config_panel.setEnabled(True)
        self._update_start_button()

    def _on_thread_finished(self, thread: QThread) -> None:
        """Remove a finished thread from the active list."""
        if thread in self._threads:
            self._threads.remove(thread)
    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_tasks(
        self,
        files: List[Path],
        mode: str,
        output_root: Optional[Path],
    ) -> List[ConversionTask]:
        """
        Convert a flat list of checked file paths into
        :class:`ConversionTask` objects.

        For single-root mode each source file **must** be nested inside
        an ``Artist/Album`` folder structure.  Files that do not meet
        this requirement are skipped with a warning emitted via the
        :class:`LogManager`.

        For per-folder mode the ``converted/`` sub-directory is placed
        next to the source file as usual.
        """
        tasks: List[ConversionTask] = []

        for src in files:
            if mode == OutputPanel.MODE_SINGLE:
                rel = self._artist_album_relative(src)
                if rel is None:
                    self._log_manager.warning(
                        f"Skipping {src.name}: file must reside inside "
                        f"an Artist/Album folder hierarchy"
                    )
                    continue
                dest = output_root / rel.with_suffix(".dsf")
            else:
                dest = src.parent / "converted" / (src.stem + ".dsf")
            tasks.append(ConversionTask(source=src, destination=dest))
        return tasks

    @staticmethod
    def _artist_album_relative(file_path: Path) -> Optional[Path]:
        """
        Derive the relative ``Artist/Album[/Disc]/filename`` path from
        an absolute *file_path*.

        The algorithm walks up from the file and collects at most three
        levels (Artist, Album, optional Disc), stopping when it reaches
        the filesystem root.

        Returns ``None`` when fewer than two parent directories exist
        above the file.
        """
        parts = file_path.parts
        if len(parts) < 4:
            return None

        # Collect up to 3 levels above the filename.
        levels = list(parts[-4:-1])   # e.g. ['Diana Krall', 'Album', 'CD1']
        filename = parts[-1]

        # If only 2 levels, that is Artist/Album.
        # If 3 levels, that is Artist/Album/Disc.
        return Path(*levels) / filename

    def _warn_rejected_files(
        self, rejected: List[Tuple[Path, str]], valid_count: int
    ) -> bool:
        """
        Show a dialog listing path-rejected files with three options:

        * **Continue** — proceed without the rejected files.
        * **Export list** — save rejected paths to a text file and
          return ``False`` so the user can fix them.
        * **Cancel** — abort the entire conversion.

        Returns
        -------
        bool
            ``True`` when the user chose to continue despite the
            rejected files, ``False`` otherwise.
        """
        if not rejected:
            return True

        lines = []
        for rp, reason in rejected:
            lines.append(f"• {rp.name}")
            lines.append(f"  {reason}")
        detail = "\n".join(lines)

        msg = (
            f"{len(rejected)} file(s) have unsafe characters in their "
            f"paths and will be **skipped**.\n\n"
            f"{detail}\n\n"
            f"{valid_count} file(s) remain valid for conversion."
        )

        dlg = QMessageBox(self)
        dlg.setWindowTitle("Path Validation Warning")
        dlg.setText(msg)
        dlg.setIcon(QMessageBox.Warning)

        btn_continue = dlg.addButton("Continue Anyway", QMessageBox.AcceptRole)
        btn_export = dlg.addButton("Export List...", QMessageBox.ActionRole)
        btn_cancel = dlg.addButton("Cancel", QMessageBox.RejectRole)

        dlg.exec()

        clicked = dlg.clickedButton()

        if clicked is btn_continue:
            return True

        if clicked is btn_export:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Rejected Files List",
                str(Path.home() / "rejected_files.txt"),
                "Text Files (*.txt)",
            )
            if path:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("Rejected files — DFF2DSF GUI\n")
                    fh.write("=" * 60 + "\n\n")
                    for rp, reason in rejected:
                        fh.write(f"{rp}\n  {reason}\n\n")
                self._log_manager.info(
                    f"Rejected files list exported to {path}"
                )
            return False

        # Cancel
        return False

    def _handle_destination_collisions(
        self, tasks: List[ConversionTask]
    ) -> List[ConversionTask, bool]:
        """
        Scan *tasks* for pre-existing destination files and let the
        user decide how to handle them: **skip** or **overwrite**.

        Returns
        -------
        List[ConversionTask, overwrite]
            The (possibly filtered) task list ready for execution.
            The overwrite boolean flag, True or False
        """
        collisions = [t for t in tasks if t.destination.exists()]
        if not collisions:
            return tasks, False

        names = "\n".join(
            f"  • {t.destination.name}" for t in collisions[:15]
        )
        suffix = (
            f"\n  ... and {len(collisions) - 15} more"
            if len(collisions) > 15
            else ""
        )

        msg = (
            f"{len(collisions)} destination file(s) already exist:\n\n"
            f"{names},{suffix}\n\n"
            f"How should these be handled?"
        )

        dlg = QMessageBox(self)
        dlg.setWindowTitle("Destination Files Already Exist")
        dlg.setText(msg)
        dlg.setIcon(QMessageBox.Warning)

        btn_skip = dlg.addButton("Skip Existing", QMessageBox.AcceptRole)
        btn_overwrite = dlg.addButton("Overwrite All", QMessageBox.DestructiveRole)
        btn_cancel = dlg.addButton("Cancel", QMessageBox.RejectRole)

        dlg.exec()
        clicked = dlg.clickedButton()

        if clicked is btn_cancel:
            return [], False
        if clicked is btn_overwrite:
            return tasks, True

        # Skip: filter out tasks whose destination already exists.
        return [t for t in tasks if not t.destination.exists()], False


    def _confirm_conversion(self, tasks: List[ConversionTask]) -> bool:
        """
        Show a summary dialog before conversion begins.

        Returns ``True`` when the user confirms, ``False`` to abort.
        """
        folders = sorted({t.destination.parent for t in tasks})
        folder_list = "\n".join(f"  • {f}" for f in folders[:5])
        if len(folders) > 5:
            folder_list += f"\n  ... and {len(folders) - 5} more"

        msg = (
            f"Ready to convert {len(tasks)} file(s) to "
            f"{len(folders)} destination folder(s):\n\n"
            f"{folder_list}\n\n"
            f"Proceed?"
        )

        dlg = QMessageBox(self)
        dlg.setWindowTitle("Confirm Conversion")
        dlg.setText(msg)
        dlg.setIcon(QMessageBox.Question)
        dlg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dlg.setDefaultButton(QMessageBox.Yes)

        return dlg.exec() == QMessageBox.Yes



                                                                                                                                                                                                                                                                                                                                                                                              