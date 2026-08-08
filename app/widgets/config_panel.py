"""
Configuration panel for HiResToolsGUI.

Provides widgets to:
* Locate the ``dff2dsf`` and ``sacd_extract`` binaries.
* Display validation status for each binary path.
* Persist all settings via :class:`QSettings`.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ConfigPanel(QGroupBox):
    """
    Group-box containing binary-path selection for both converters.

    Signals
    -------
    dff2dsf_changed(path):
        Emitted when the dff2dsf binary path changes.
    sacd_extract_changed(path):
        Emitted when the sacd_extract binary path changes.
    """

    dff2dsf_changed = Signal(Path)
    sacd_extract_changed = Signal(Path)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Converter Configuration", parent)
        self._settings = QSettings()
        self._dff2dsf_path: Optional[Path] = None
        self._sacd_extract_path: Optional[Path] = None
        self._build_ui()
        self._restore_settings()

    # ------------------------------------------------------------------
    # Public queries
    # ------------------------------------------------------------------

    def dff2dsf_path(self) -> Optional[Path]:
        """Return the configured dff2dsf binary path, or ``None``."""
        return self._dff2dsf_path

    def sacd_extract_path(self) -> Optional[Path]:
        """Return the configured sacd_extract binary path, or ``None``."""
        return self._sacd_extract_path

    def set_dff2dsf_status(self, valid: bool, message: str) -> None:
        """Update the validation indicator for dff2dsf."""
        self._set_status(self._lbl_dff2dsf_status, valid, message)

    def set_sacd_extract_status(self, valid: bool, message: str) -> None:
        """Update the validation indicator for sacd_extract."""
        self._set_status(self._lbl_sacd_status, valid, message)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # -- dff2dsf row --
        layout.addWidget(QLabel("dff2dsf binary:"))
        dff2dsf_row = QHBoxLayout()
        self._edit_dff2dsf = QLineEdit()
        self._edit_dff2dsf.setPlaceholderText("/usr/local/bin/dff2dsf")
        self._edit_dff2dsf.textChanged.connect(self._on_dff2dsf_text_changed)

        self._btn_dff2dsf_browse = QPushButton("Browse...")
        self._btn_dff2dsf_browse.clicked.connect(self._on_dff2dsf_browse)

        self._lbl_dff2dsf_status = QLabel("")
        self._lbl_dff2dsf_status.setFixedWidth(90)
        self._lbl_dff2dsf_status.setAlignment(Qt.AlignCenter)

        dff2dsf_row.addWidget(self._edit_dff2dsf, 1)
        dff2dsf_row.addWidget(self._btn_dff2dsf_browse)
        dff2dsf_row.addWidget(self._lbl_dff2dsf_status)
        layout.addLayout(dff2dsf_row)

        # -- sacd_extract row --
        layout.addWidget(QLabel("sacd_extract binary:"))
        sacd_row = QHBoxLayout()
        self._edit_sacd = QLineEdit()
        self._edit_sacd.setPlaceholderText("/usr/local/bin/sacd_extract")
        self._edit_sacd.textChanged.connect(self._on_sacd_text_changed)

        self._btn_sacd_browse = QPushButton("Browse...")
        self._btn_sacd_browse.clicked.connect(self._on_sacd_browse)

        self._lbl_sacd_status = QLabel("")
        self._lbl_sacd_status.setFixedWidth(90)
        self._lbl_sacd_status.setAlignment(Qt.AlignCenter)

        sacd_row.addWidget(self._edit_sacd, 1)
        sacd_row.addWidget(self._btn_sacd_browse)
        sacd_row.addWidget(self._lbl_sacd_status)
        layout.addLayout(sacd_row)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _restore_settings(self) -> None:
        """Load previously saved paths from QSettings."""
        dff2dsf = self._settings.value("dff2dsf_binary", "")
        if dff2dsf:
            self._edit_dff2dsf.setText(dff2dsf)
        else:
            self._auto_detect("dff2dsf", self._edit_dff2dsf)

        sacd = self._settings.value("sacd_extract_binary", "")
        if sacd:
            self._edit_sacd.setText(sacd)
        else:
            self._auto_detect("sacd_extract", self._edit_sacd)

    @staticmethod
    def _auto_detect(name: str, edit: QLineEdit) -> None:
        """Search for *name* on ``$PATH`` and pre-fill the text field."""
        located = shutil.which(name)
        if located:
            edit.setText(located)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def _on_dff2dsf_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Locate dff2dsf binary", str(Path.home()), "All Files (*)",
        )
        if path:
            self._edit_dff2dsf.setText(path)

    @Slot(str)
    def _on_dff2dsf_text_changed(self, text: str) -> None:
        text = text.strip()
        if not text:
            self._dff2dsf_path = None
            self._settings.remove("dff2dsf_binary")
            return
        self._dff2dsf_path = Path(text).expanduser().resolve()
        self._settings.setValue("dff2dsf_binary", str(self._dff2dsf_path))
        self.dff2dsf_changed.emit(self._dff2dsf_path)

    @Slot()
    def _on_sacd_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Locate sacd_extract binary", str(Path.home()), "All Files (*)",
        )
        if path:
            self._edit_sacd.setText(path)

    @Slot(str)
    def _on_sacd_text_changed(self, text: str) -> None:
        text = text.strip()
        if not text:
            self._sacd_extract_path = None
            self._settings.remove("sacd_extract_binary")
            return
        self._sacd_extract_path = Path(text).expanduser().resolve()
        self._settings.setValue("sacd_extract_binary", str(self._sacd_extract_path))
        self.sacd_extract_changed.emit(self._sacd_extract_path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _set_status(label: QLabel, valid: bool, message: str) -> None:
        if valid:
            label.setText("OK")
            label.setStyleSheet("color: #2ecc71; font-weight: bold;")
        else:
            label.setText("NOT FOUND")
            label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        label.setToolTip(message)



