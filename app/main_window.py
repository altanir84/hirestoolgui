"""
Main application window for HiResToolsGUI.

Wires together the config panel, file tree, output panel, SACD options,
and progress panel.  Manages the conversion lifecycle for both DFF and
ISO sources.
"""

from __future__ import annotations

import os
import re
import threading
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QThread, Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
    )

from app.core.converter_worker import ConversionTask, ConverterWorker
from app.core.path_validator import PathValidator
from app.core.tag_preserver import TagPreserver
from app.utils.logger import LogManager
from app.widgets.config_panel import ConfigPanel
from app.widgets.file_panel import FilePanel
from app.widgets.output_panel import OutputPanel
from app.widgets.progress_panel import ProgressPanel
from app.widgets.sacd_panel import SacdPanel


class MainWindow(QMainWindow):
    """
    Top-level window of HiResToolsGUI.

    ┌──────────────────────────────────────────┐
    │  ConfigPanel  (dff2dsf + sacd_extract)   │
    ├──────────────────────────────────────────┤
    │  FilePanel          │  OutputPanel       │
    │  (tree + buttons)   │  (mode selection)  │
    │                     │  SacdPanel         │
    ├─────────────────────┴────────────────────┤
    │  [Start Conversion]                      │
    │  ProgressPanel  (bar + log)              │
    └──────────────────────────────────────────┘
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HiResToolsGUI")
        self.setMinimumSize(900, 700)

        self._log_manager = LogManager()
        self._cancel_event = threading.Event()
        self._tag_preserver = TagPreserver()
        self._threads: List[QThread] = []
        self._workers: List[ConverterWorker] = []
        self._task_map: Dict[str, str] = {}
        self._running = False
        self._completed_tasks = 0
        self._success_count = 0
        self._failed_count = 0
        self._total_tasks = 0

        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._poll_progress)

        self._build_ui()
        self._connect_signals()
        self._update_binary_statuses()
        self._update_start_button()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Assemble the widget tree and set up the vertical splitter."""
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(4, 4, 4, 4)

        # -- Config panel --
        self._config_panel = ConfigPanel()
        root_layout.addWidget(self._config_panel)

        # -- Vertical splitter --
        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.setChildrenCollapsible(False)

        # Upper widget -------------------------------------------------
        upper = QWidget()
        upper_layout = QHBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)

        self._file_panel = FilePanel()
        self._file_panel.set_warning_callback(self._log_manager.warning)

        right_side = QVBoxLayout()
        right_side.setContentsMargins(0, 0, 0, 0)
        self._output_panel = OutputPanel()
        self._sacd_panel = SacdPanel()
        self._sacd_panel.setEnabled(False)
        right_side.addWidget(self._output_panel)
        right_side.addWidget(self._sacd_panel)
        right_side.addStretch()

        right_widget = QWidget()
        right_widget.setLayout(right_side)

        upper_layout.addWidget(self._file_panel, 3)
        upper_layout.addWidget(right_widget, 1)

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
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self._splitter, 1)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """Connect all child-widget signals to MainWindow slots."""
        self._config_panel.dff2dsf_changed.connect(self._on_binary_changed)
        self._config_panel.sacd_extract_changed.connect(self._on_binary_changed)
        self._output_panel.mode_changed.connect(self._on_mode_changed)
        self._file_panel.scan_completed.connect(self._update_start_button)
        self._file_panel.selection_changed.connect(self._on_selection_changed)
        self._sacd_panel.options_changed.connect(self._update_start_button)
        self._btn_start.clicked.connect(self._on_start)
        self._progress_panel.cancel_requested.connect(self._on_cancel)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_binary(path: Optional[Path]) -> bool:
        """Return ``True`` when *path* exists and is executable."""
        if path is None:
            return False
        return path.is_file() and os.access(str(path), os.X_OK)

    def _validate_output(self) -> bool:
        """Return ``True`` when the output configuration is valid."""
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

        checked = self._file_panel.checked_files()
        if not checked:
            return False

        has_dff = any(f.suffix.lower() == ".dff" for f in checked)
        has_iso = any(f.suffix.lower() == ".iso" for f in checked)

        if has_dff and not self._validate_binary(
            self._config_panel.dff2dsf_path()
        ):
            return False
        if has_iso and not self._validate_binary(
            self._config_panel.sacd_extract_path()
        ):
            return False

        if not self._validate_output():
            return False

        if has_iso:
            if (
                not self._sacd_panel.stereo()
                and not self._sacd_panel.multichannel()
            ):
                return False

        return True

    # ------------------------------------------------------------------
    # Slots – UI state updates
    # ------------------------------------------------------------------

    @Slot(Path)
    def _on_binary_changed(self, _path: Path) -> None:
        self._update_binary_statuses()
        self._update_start_button()

    @Slot(str, object)
    def _on_mode_changed(self, _mode: str, _root: Optional[Path]) -> None:
        self._update_start_button()

    @Slot(int)
    def _on_selection_changed(self, _count: int) -> None:
        checked = self._file_panel.checked_files()
        has_iso = any(f.suffix.lower() == ".iso" for f in checked)
        self._sacd_panel.setEnabled(has_iso)
        self._update_start_button()

    def _update_binary_statuses(self) -> None:
        """Refresh the validation indicators for both binaries."""
        dff2dsf = self._config_panel.dff2dsf_path()
        if dff2dsf and self._validate_binary(dff2dsf):
            self._config_panel.set_dff2dsf_status(True, f"Found: {dff2dsf}")
        else:
            self._config_panel.set_dff2dsf_status(
                False, "dff2dsf binary not found or not executable"
            )

        sacd = self._config_panel.sacd_extract_path()
        if sacd and self._validate_binary(sacd):
            self._config_panel.set_sacd_extract_status(True, f"Found: {sacd}")
        else:
            self._config_panel.set_sacd_extract_status(
                False, "sacd_extract binary not found or not executable"
            )

    @Slot()
    def _update_start_button(self, _unused: int = 0) -> None:
        """Enable or disable the Start button based on current state."""
        self._btn_start.setEnabled(self._can_start())

    # ------------------------------------------------------------------
    # Slots – conversion lifecycle
    # ------------------------------------------------------------------

    @Slot()
    def _on_start(self) -> None:
        """Validate inputs, build tasks, confirm, and spawn worker thread."""
        checked = self._file_panel.checked_files()
        has_dff = any(f.suffix.lower() == ".dff" for f in checked)
        has_iso = any(f.suffix.lower() == ".iso" for f in checked)

        if has_dff and not self._validate_binary(
            self._config_panel.dff2dsf_path()
        ):
            QMessageBox.warning(
                self, "Invalid Binary",
                "The dff2dsf binary path is invalid.",
            )
            return

        if has_iso and not self._validate_binary(
            self._config_panel.sacd_extract_path()
        ):
            QMessageBox.warning(
                self, "Invalid Binary",
                "The sacd_extract binary path is invalid.",
            )
            return

        if not self._validate_output():
            QMessageBox.warning(
                self, "Invalid Output",
                "Please specify a valid output root directory.",
            )
            return

        valid, rejected = PathValidator.filter_batch(checked)

        if rejected:
            for rp, reason in rejected:
                self._log_manager.warning(
                    f"Path rejected: {rp.name} — {reason}"
                )

        if not self._warn_rejected_files(rejected, len(valid)):
            return

        if not valid:
            QMessageBox.information(
                self, "Nothing to Convert",
                "No valid files are selected for conversion.",
            )
            return

        mode = self._output_panel.output_mode()
        output_root = self._output_panel.output_root()
        tasks = self._build_tasks(valid, mode, output_root)

        if not tasks:
            QMessageBox.information(
                self, "Nothing to Convert",
                "All selected files were skipped during task building.",
            )
            return

        tasks, overwrite = self._handle_destination_collisions(tasks)
        if not tasks:
            return

        if not self._confirm_conversion(tasks):
            return

        # Cache ID3 tags for DFF files before conversion.
        for task in tasks:
            if task.converter == "dff2dsf":
                self._tag_preserver.cache_tags(task.source)

        # Map sources to converter types for tag restoration.
        self._task_map = {str(t.source): t.converter for t in tasks}

        self._running = True
        self._cancel_event.clear()
        self._btn_start.setEnabled(False)
        self._completed_tasks = 0
        self._success_count = 0
        self._failed_count = 0
        self._total_tasks = len(tasks)
        self._progress_panel.reset()
        self._progress_panel.set_overall_progress(0, self._total_tasks)

        self._file_panel.setEnabled(False)
        self._output_panel.setEnabled(False)
        self._config_panel.setEnabled(False)
        self._sacd_panel.setEnabled(False)

        self._log_manager.info(
            f"Starting conversion of {len(tasks)} file(s) (mode={mode})"
        )

        thread = QThread()
        worker = ConverterWorker(
            str(self._config_panel.dff2dsf_path() or ""),
            str(self._config_panel.sacd_extract_path() or ""),
            tasks,
            sacd_stereo=self._sacd_panel.stereo(),
            sacd_multichannel=self._sacd_panel.multichannel(),
            sacd_cue=self._sacd_panel.cue_sheet(),
            sacd_output_format=self._sacd_panel.output_format_flag(),
            cancel_event=self._cancel_event,
            overwrite=overwrite,
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.task_started.connect(self._on_task_started)
        worker.task_progress.connect(self._on_task_progress)
        worker.task_finished.connect(self._on_task_finished)
        worker.task_skipped.connect(self._on_task_skipped)
        worker.all_done.connect(self._on_worker_done)
        thread.finished.connect(lambda t=thread: self._on_thread_finished(t))

        self._threads.append(thread)
        self._workers.append(worker)

        thread.start()
        self._progress_timer.start(200)

    @Slot()
    def _on_cancel(self) -> None:
        """Request graceful cancellation."""
        self._cancel_event.set()
        self._log_manager.warning(
            "Cancellation requested — finishing current file..."
        )
        self._progress_panel._btn_cancel.setEnabled(False)

    @Slot(str, str)
    def _on_task_started(self, source: str, dest: str) -> None:
        self._log_manager.info(f"Converting: {Path(source).name}")
        self._progress_panel.append_log(self._log_manager.entries()[-1])

    @Slot(int, int, str)
    def _on_task_progress(self, current: int, total: int, _message: str) -> None:
        self._progress_panel.set_file_progress(current, total)
        self._log_manager.info(_message)
        self._progress_panel.append_log(self._log_manager.entries()[-1])

    @Slot()
    def _poll_progress(self) -> None:
        """Poll the worker's progress queue and update the UI."""
        for worker in self._workers:
            while True:
                item = worker.get_progress()
                if item is None:
                    break
                current, total, message = item
                self._progress_panel.set_file_progress(current, total)
                # Extract track filename from the progress message.
                
                match = re.search(r"Processing\s+\[(.+)\]", message)

                if match:
                    track_name = Path(match.group(1)).name
                    self._log_manager.info(
                        f"  Track {current}/{total}: {track_name}"
                    )
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

        converter_type = self._task_map.get(source, "")

        if exit_code == 0:
            self._success_count += 1
            self._log_manager.success(f"OK: {Path(source).name}")

            # Restore ID3 tags for DFF conversions.
            if converter_type == "dff2dsf":
                applied = self._tag_preserver.apply_tags(
                    Path(source), Path(dest)
                )
                if not applied:
                    self._log_manager.warning(
                        f"Could not preserve tags for: {Path(source).name}"
                    )

            # Move SACD tracks up one level (sacd_extract creates an
            # extra subfolder named after the ISO).
            if converter_type == "sacd_extract":
                dest_path = Path(dest)
                dest_dir = dest_path.parent
                for subdir in dest_dir.iterdir():
                    if subdir.is_dir():
                        for f in subdir.iterdir():
                            shutil.move(str(f), str(dest_dir / f.name))
                        subdir.rmdir()
                        break
        else:
            self._failed_count += 1
            self._log_manager.error(
                f"FAILED: {Path(source).name} (exit={exit_code})"
            )
            if stderr and exit_code != 0:
                self._log_manager.error(f"  stderr: {stderr}")

        self._progress_panel.append_log(self._log_manager.entries()[-1])





    @Slot(str, str)
    def _on_task_skipped(self, source: str, reason: str) -> None:
        self._log_manager.warning(
            f"SKIPPED: {Path(source).name} — {reason}"
        )
        self._progress_panel.append_log(self._log_manager.entries()[-1])

    @Slot()
    def _on_worker_done(self) -> None:
        """Finalise the UI when the worker signals completion."""
        self._running = False
        for t in self._threads:
            if t.isRunning():
                t.quit()
                t.wait(3000)
        self._workers.clear()
        self._tag_preserver.clear()

        self._progress_panel.conversion_finished()
        self._progress_timer.stop()
        # self._progress_panel.set_file_progress(0, 0)  # DEBUG
        # self._progress_panel._bar_file.setVisible(False)

        self._log_manager.info("All conversions completed.")
        self._log_manager.info(
            f"Summary: {self._success_count} succeeded, "
            f"{self._failed_count} failed, "
            f"{self._total_tasks} total"
        )
        self._log_manager.info(
            f"Log file: {self._log_manager._log_dir}"
        )

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
    # Task building
    # ------------------------------------------------------------------

    def _build_tasks(
        self,
        files: List[Path],
        mode: str,
        output_root: Optional[Path],
    ) -> List[ConversionTask]:
        """
        Build :class:`ConversionTask` objects for each file.

        DFF files use ``dff2dsf``; ISO files use ``sacd_extract``.
        For ISO files in single-root mode, the output directory points
        to the *Artist* folder because ``sacd_extract -y`` creates the
        album sub-folder automatically.
        """
        tasks: List[ConversionTask] = []

        for src in files:
            if src.suffix.lower() == ".iso":
                if mode == OutputPanel.MODE_SINGLE:
                    dest_dir = self._iso_dest_dir(src, output_root)
                    if dest_dir is None:
                        self._log_manager.warning(
                            f"Skipping {src.name}: file must reside "
                            f"inside an Artist/Album folder hierarchy"
                        )
                        continue
                    # sacd_extract -y creates the album folder internally.                
                    dest = dest_dir / (src.stem + ".dsf")
                else:
                    dest_dir = src.parent / "converted"
                    dest = dest_dir / (src.stem + ".dsf")
                tasks.append(ConversionTask(
                    source=src, destination=dest, converter="sacd_extract",
                ))
            else:
                if mode == OutputPanel.MODE_SINGLE:
                    rel = self._artist_album_relative(src)
                    if rel is None:
                        self._log_manager.warning(
                            f"Skipping {src.name}: file must reside "
                            f"inside an Artist/Album folder hierarchy"
                        )
                        continue
                    dest = output_root / rel.with_suffix(".dsf")
                else:
                    dest = src.parent / "converted" / (src.stem + ".dsf")
                tasks.append(ConversionTask(
                    source=src, destination=dest, converter="dff2dsf",
                ))
        return tasks


    @staticmethod
    def _artist_album_relative(file_path: Path) -> Optional[Path]:
        """
        Derive the relative ``Artist/Album[/Disc]/filename`` path from
        an absolute *file_path*.

        Returns ``None`` when fewer than two parent directories exist
        above the file.
        """
        parts = file_path.parts
        if len(parts) < 4:
            return None
        levels = list(parts[-4:-1])
        filename = parts[-1]
        return Path(*levels) / filename
    

    @staticmethod
    def _iso_dest_dir(file_path: Path, output_root: Path) -> Optional[Path]:
        """
        Compute the destination directory for an ISO extraction.

        Returns ``output_root/Artist/Album[/Disc]`` so that
        ``sacd_extract -y <dir>`` writes tracks into the correct
        location without creating an extra nested folder.
        """
        parts = file_path.parts
        if len(parts) < 4:
            return None
        # parts[-4:-1] = [..., Artist, Album] or [..., Artist, Album, CD1]
        levels = list(parts[-4:-1])
        return output_root / Path(*levels)


    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------

    def _warn_rejected_files(
        self, rejected: List[Tuple[Path, str]], valid_count: int
    ) -> bool:
        """
        Show a dialog listing path-rejected files.

        Loops until the user chooses Continue or Cancel.  Export List
        saves the list and re-opens the dialog.
        """
        if not rejected:
            return True

        while True:
            lines = []
            for rp, reason in rejected:
                lines.append(f"• {rp.name}")
                lines.append(f"  {reason}")
            detail = "\n".join(lines)

            msg = (
                f"{len(rejected)} file(s) have unsafe characters in "
                f"their paths and will be skipped.\n\n"
                f"{detail}\n\n"
                f"{valid_count} file(s) remain valid for conversion."
            )

            dlg = QMessageBox(self)
            dlg.setWindowTitle("Path Validation Warning")
            dlg.setText(msg)
            dlg.setIcon(QMessageBox.Warning)

            btn_continue = dlg.addButton(
                "Continue Anyway", QMessageBox.AcceptRole
            )
            btn_export = dlg.addButton(
                "Export List...", QMessageBox.ActionRole
            )
            btn_cancel = dlg.addButton("Cancel", QMessageBox.RejectRole)

            dlg.exec()
            clicked = dlg.clickedButton()

            if clicked is btn_continue:
                return True

            if clicked is btn_cancel:
                return False

            if clicked is btn_export:
                path, _ = QFileDialog.getSaveFileName(
                    self, "Save Rejected Files List",
                    str(Path.home() / "rejected_files.txt"),
                    "Text Files (*.txt)",
                )
                if path:
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write("Rejected files — HiResToolsGUI\n")
                        fh.write("=" * 60 + "\n\n")
                        for rp, reason in rejected:
                            fh.write(f"{rp}\n  {reason}\n\n")
                    self._log_manager.info(
                        f"Rejected files list exported to {path}"
                    )

    def _handle_destination_collisions(
        self, tasks: List[ConversionTask]
    ) -> Tuple[List[ConversionTask], bool]:
        """
        Scan *tasks* for pre-existing destination files.

        Returns ``(tasks, overwrite)``.
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

        btn_skip = dlg.addButton(
            "Skip Existing", QMessageBox.AcceptRole
        )
        btn_overwrite = dlg.addButton(
            "Overwrite All", QMessageBox.DestructiveRole
        )
        btn_cancel = dlg.addButton("Cancel", QMessageBox.RejectRole)

        dlg.exec()
        clicked = dlg.clickedButton()

        if clicked is btn_cancel:
            return [], False
        if clicked is btn_overwrite:
            return tasks, True
        return [t for t in tasks if not t.destination.exists()], False

    def _confirm_conversion(self, tasks: List[ConversionTask]) -> bool:
        """
        Show a summary dialog before conversion begins.

        Returns ``True`` when the user confirms.
        """
        folders = sorted({t.destination.parent for t in tasks})
        folder_list = "\n".join(f"  • {f}" for f in folders[:5])
        if len(folders) > 5:
            folder_list += f"\n  ... and {len(folders) - 5} more"

        iso_count = sum(
            1 for t in tasks if t.converter == "sacd_extract"
        )
        dff_count = sum(
            1 for t in tasks if t.converter == "dff2dsf"
        )

        msg = (
            f"Ready to convert {len(tasks)} file(s) to "
            f"{len(folders)} destination folder(s):\n\n"
            f"  DFF → dff2dsf: {dff_count}\n"
            f"  ISO → sacd_extract: {iso_count}\n\n"
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



