"""
Main application window for HiResToolsGUI.

Wires together the config panel, file tree, output panel, SACD options,
and progress panel.  Delegates conversion orchestration, task building,
tag assurance, and dialogs to dedicated modules.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.core.conversion_orchestrator import ConversionOrchestrator
from app.core.path_validator import PathValidator
from app.core.tag_assurance import TagAssurance
from app.core.tag_preserver import TagPreserver
from app.core.task_builder import TaskBuilder
from app.utils.logger import ErrorLogManager, LogManager
from app.widgets.config_panel import ConfigPanel
from app.widgets.dialogs import Dialogs
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
        self.resize(1200, 900)

        self._log_manager = LogManager()
        self._error_log = ErrorLogManager()
        self._tag_preserver = TagPreserver()
        self._task_builder = TaskBuilder(self._log_manager, self._error_log)
        self._tag_assurance = TagAssurance(self._tag_preserver)
        self._orchestrator: Optional[ConversionOrchestrator] = None
        self._running = False

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

        self._config_panel = ConfigPanel()
        root_layout.addWidget(self._config_panel)

        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.setChildrenCollapsible(False)

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

        self._splitter.addWidget(upper)
        self._splitter.addWidget(lower)
        self._splitter.setStretchFactor(0, 2)
        self._splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self._splitter, 1)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """Connect all child-widget signals to MainWindow slots."""
        self._config_panel.dff2dsf_changed.connect(
            self._on_binary_changed
        )
        self._config_panel.sacd_extract_changed.connect(
            self._on_binary_changed
        )
        self._output_panel.mode_changed.connect(self._on_mode_changed)
        self._file_panel.scan_completed.connect(
            self._update_start_button
        )
        self._file_panel.selection_changed.connect(
            self._on_selection_changed
        )
        self._sacd_panel.options_changed.connect(
            self._update_start_button
        )
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
    def _on_mode_changed(
        self, _mode: str, _root: Optional[Path]
    ) -> None:
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
            self._config_panel.set_dff2dsf_status(
                True, f"Found: {dff2dsf}"
            )
        else:
            self._config_panel.set_dff2dsf_status(
                False, "dff2dsf binary not found or not executable"
            )

        sacd = self._config_panel.sacd_extract_path()
        if sacd and self._validate_binary(sacd):
            self._config_panel.set_sacd_extract_status(
                True, f"Found: {sacd}"
            )
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
        """Validate inputs, build tasks, confirm, and spawn orchestrator."""
        checked = self._file_panel.checked_files()
        keep_folder=self._sacd_panel.keep_folder(),
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
                file_type = (
                    "ISO" if rp.suffix.lower() == ".iso" else "DFF"
                )
                self._error_log.add_skipped(
                    str(rp), file_type, reason
                )

        if not Dialogs.warn_rejected_files(
            self, rejected, len(valid)
        ):
            return

        if not valid:
            QMessageBox.information(
                self, "Nothing to Convert",
                "No valid files are selected for conversion.",
            )
            return

        mode = self._output_panel.output_mode()
        output_root = self._output_panel.output_root()
        tasks = self._task_builder.build(valid, mode, output_root)

        if not tasks:
            QMessageBox.information(
                self, "Nothing to Convert",
                "All selected files were skipped during task building.",
            )
            return

        tasks, overwrite = Dialogs.handle_destination_collisions(
            self, tasks
        )
        if not tasks:
            return

        if not Dialogs.confirm_conversion(self, tasks):
            return

        # Ensure DFF files have minimum tags before conversion.
        dff_files = [
            t.source for t in tasks if t.converter == "dff2dsf"
        ]
        self._tag_assurance.ensure_tags(dff_files)

        self._running = True
        self._btn_start.setEnabled(False)

        self._file_panel.setEnabled(False)
        self._output_panel.setEnabled(False)
        self._config_panel.setEnabled(False)
        self._sacd_panel.setEnabled(False)

        self._orchestrator = ConversionOrchestrator(
            log_manager=self._log_manager,
            error_log=self._error_log,
            tag_preserver=self._tag_preserver,
            progress_panel=self._progress_panel,
            binary_dff2dsf=str(
                self._config_panel.dff2dsf_path() or ""
            ),
            binary_sacd_extract=str(
                self._config_panel.sacd_extract_path() or ""
            ),
            sacd_stereo=self._sacd_panel.stereo(),
            sacd_multichannel=self._sacd_panel.multichannel(),
            sacd_cue=self._sacd_panel.cue_sheet(),
            sacd_output_format=self._sacd_panel.output_format_flag(),
            overwrite=overwrite,
        )
        self._orchestrator.finished.connect(self._on_batch_finished)
        self._orchestrator.start(tasks)

    @Slot()
    def _on_cancel(self) -> None:
        """Request graceful cancellation."""
        if self._orchestrator is not None:
            self._orchestrator.cancel()
        self._progress_panel._btn_cancel.setEnabled(False)

    @Slot(int, int, int)
    def _on_batch_finished(
        self, _success: int, _failed: int, _total: int
    ) -> None:
        """Re-enable UI after batch completion."""
        self._running = False
        self._file_panel.setEnabled(True)
        self._output_panel.setEnabled(True)
        self._config_panel.setEnabled(True)
        self._update_start_button()
