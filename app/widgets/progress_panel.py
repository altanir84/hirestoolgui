"""
Progress and logging panel displayed at the bottom of the main window.

Shows a dual progress bar (file-level + overall), a cancellable log
view, and the Cancel button for aborting a running batch.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.utils.logger import LogEntry, LogManager


class ProgressPanel(QWidget):
    """
    Bottom panel combining progress bars and a read-only log view.

    Signals
    -------
    cancel_requested():
        Emitted when the user clicks the Cancel button.
    """

    cancel_requested = Signal()

    # Colour map for log levels.
    _LEVEL_COLORS = {
        "INFO":     QColor("#bdc3c7"),
        "WARNING":  QColor("#f39c12"),
        "ERROR":    QColor("#e74c3c"),
        "SUCCESS":  QColor("#2ecc71"),
    }

    def __init__(
        self,
        log_manager: LogManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._log_manager = log_manager
        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset progress bars and enable the Cancel button."""
        self._bar_overall.setValue(0)
        self._lbl_overall.setText("Ready")
        self._btn_cancel.setEnabled(True)
        self._log_view.clear()
        self._log_manager.clear()

    def set_overall_progress(self, current: int, total: int) -> None:
        """Update the overall (task-level) progress bar."""
        self._bar_overall.setMaximum(total)
        self._bar_overall.setValue(current)
        self._lbl_overall.setText(f"{current}/{total}")

    def set_file_progress(self, current: int, total: int) -> None:
        """Update the per-track progress bar (SACD extraction only)."""
        self._bar_file.setEnabled(True)
        self._bar_file.setMaximum(total)
        self._bar_file.setValue(current)

    def append_log(self, entry: LogEntry) -> None:
        """Append a *LogEntry* to the on-screen log view."""
        color = self._LEVEL_COLORS.get(entry.level, QColor("#bdc3c7"))
        fmt = QTextCharFormat()
        fmt.setForeground(color)

        cursor = self._log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(
            f"[{entry.timestamp}] ", fmt,
        )
        cursor.insertText(f"{entry.message}\n")

        # Auto-scroll to bottom.
        self._log_view.setTextCursor(cursor)
        self._log_view.ensureCursorVisible()

    def conversion_finished(self) -> None:
        """Disable the Cancel button and mark progress as complete."""
        self._btn_cancel.setEnabled(False)
        self._bar_overall.setValue(self._bar_overall.maximum())
        # self._bar_file.setEnabled(False)
        # self._bar_file.setValue(0)
        # self._bar_file.setMaximum(1)
        self._lbl_overall.setText("Done")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # -- Progress bars row --
        progress_layout = QHBoxLayout()

        self._bar_overall = QProgressBar()
        self._bar_overall.setFormat("Overall: %v/%m")
        self._lbl_overall = QLabel("Ready")

        self._bar_file = QProgressBar()
        self._bar_file.setFormat("Track: %v/%m")
        self._bar_file.setEnabled(False)
        self._bar_file.setValue(0)
        self._bar_file.setMaximum(1)


        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.setFixedWidth(80)
        self._btn_cancel.clicked.connect(self.cancel_requested.emit)

        progress_layout.addWidget(self._bar_overall, 2)
        progress_layout.addWidget(self._bar_file, 2)
        progress_layout.addWidget(self._lbl_overall)
        progress_layout.addWidget(self._btn_cancel)

        # -- Log view --
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.document().setMaximumBlockCount(2000)
        self._log_view.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #ddd; "
            "font-family: monospace; font-size: 12px; }"
        )

        layout.addLayout(progress_layout)
        layout.addWidget(self._log_view, 1)


