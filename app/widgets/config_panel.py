"""
Configuration panel for the DFF2DSF GUI.

Provides widgets to:
* Locate the ``dff2dsf`` binary (file dialog or manual entry).
* Set the number of parallel worker threads.
* Display validation status of the binary path.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,# --- Workers spin box ---
        # workers_layout = QHBoxLayout()
        # workers_layout.addWidget(QLabel("Parallel workers:"))
        # self._spin_workers = QSpinBox()
        # self._spin_workers.setRange(1, 8)
        # self._spin_workers.setValue(2)
        # self._spin_workers.setToolTip(
        #     "Number of simultaneous conversions.\n"
        #     "Higher values increase disk I/O load."
        # )
        # workers_layout.addWidget(self._spin_workers)
        # workers_layout.addStretch()
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ConfigPanel(QGroupBox):
    """
    Group-box containing binary-path selection and worker-count controls.

    Signals
    -------
    binary_changed(path):
        Emitted when the user selects or types a new binary path.
        *path* is the absolute, resolved :class:`Path` (may not yet
        be validated).
    """

    binary_changed = Signal(Path)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Converter Configuration", parent)
        self._binary_path: Optional[Path] = None
        self._build_ui()
        self._auto_detect_binary()

    # ------------------------------------------------------------------
    # Public queries
    # ------------------------------------------------------------------

    def binary_path(self) -> Optional[Path]:
        """Return the currently configured binary path, or ``None``."""
        return self._binary_path

    def worker_count(self) -> int:
        """Return the number of parallel workers selected by the user."""
        return 1

    def set_binary_status(self, valid: bool, message: str) -> None:
        """
        Update the validation indicator next to the binary path field.

        Parameters
        ----------
        valid:
            ``True`` when the binary is found and executable.
        message:
            Human-readable status shown as a tooltip and coloured label.
        """
        if valid:
            self._lbl_status.setText("OK")
            self._lbl_status.setStyleSheet(
                "color: #2ecc71; font-weight: bold;"
            )
        else:
            self._lbl_status.setText("NOT FOUND")
            self._lbl_status.setStyleSheet(
                "color: #e74c3c; font-weight: bold;"
            )
        self._lbl_status.setToolTip(message)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- Binary path row ---
        binary_layout = QHBoxLayout()
        self._edit_binary = QLineEdit()
        self._edit_binary.setPlaceholderText(
            "/usr/local/bin/dff2dsf  or use Browse..."
        )
        self._edit_binary.textChanged.connect(self._on_binary_text_changed)

        self._btn_browse = QPushButton("Browse...")
        self._btn_browse.clicked.connect(self._on_browse)

        self._lbl_status = QLabel("")
        self._lbl_status.setFixedWidth(90)
        self._lbl_status.setAlignment(Qt.AlignCenter)

        binary_layout.addWidget(self._edit_binary, 1)
        binary_layout.addWidget(self._btn_browse)
        binary_layout.addWidget(self._lbl_status)

        # # --- Workers spin box ---
        # workers_layout = QHBoxLayout()
        # workers_layout.addWidget(QLabel("Parallel workers:"))
        # self._spin_workers = QSpinBox()
        # self._spin_workers.setRange(1, 8)
        # self._spin_workers.setValue(2)
        # self._spin_workers.setToolTip(
        #     "Number of simultaneous conversions.\n"
        #     "Higher values increase disk I/O load."
        # )
        # workers_layout.addWidget(self._spin_workers)
        # workers_layout.addStretch()

        layout.addLayout(binary_layout)
        # layout.addLayout(workers_layout)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def _on_browse(self) -> None:
        """Open a file dialog to locate the dff2dsf binary."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Locate dff2dsf binary",
            str(Path.home()),
            "All Files (*)",
        )
        if path:
            self._edit_binary.setText(path)

    @Slot(str)
    def _on_binary_text_changed(self, text: str) -> None:
        """Store the resolved path and emit binary_changed."""
        text = text.strip()
        if not text:
            self._binary_path = None
            return
        self._binary_path = Path(text).expanduser().resolve()
        self.binary_changed.emit(self._binary_path)

    @Slot()
    def _auto_detect_binary(self) -> None:
        """Search for ``dff2dsf`` on the system $PATH and pre-fill the text field when found."""
        located = shutil.which('dff2dsf')
        if located:
            self._edit_binary.setText(located)

