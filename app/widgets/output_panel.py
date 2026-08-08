"""
Output-mode configuration panel.

Lets the user choose between:
* **Single root** — all DSF files go under one directory, replicating
  the original sub-folder structure.
* **Per folder** — each DFF file gets a ``converted/`` sub-folder next
  to it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class OutputPanel(QGroupBox):
    """
    Group-box with radio buttons for output mode and an optional
    directory picker for the single-root mode.

    Signals
    -------
    mode_changed(mode, root_path):
        Emitted whenever the mode or root path changes.
        *mode* is ``"single_root"`` or ``"per_folder"``.
        *root_path* is ``None`` for per-folder mode.
    """

    MODE_SINGLE = "single_root"
    MODE_PER = "per_folder"

    mode_changed = Signal(str, object)  # (mode: str, root: Optional[Path])

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Output Mode", parent)
        self._build_ui()

    # ------------------------------------------------------------------
    # Public queries
    # ------------------------------------------------------------------

    def output_mode(self) -> str:
        """Return the currently selected mode string."""
        if self._radio_single.isChecked():
            return self.MODE_SINGLE
        return self.MODE_PER

    def output_root(self) -> Optional[Path]:
        """
        Return the single-root directory path, or ``None`` if
        per-folder mode is active or the field is empty.
        """
        if self.output_mode() != self.MODE_SINGLE:
            return None
        text = self._edit_root.text().strip()
        if not text:
            return None
        return Path(text).expanduser().resolve()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- Radio buttons ---
        self._radio_single = QRadioButton(
            "Single output root (replicates sub-folder structure)"
        )
        self._radio_per = QRadioButton(
            "Per-folder (creates 'converted/' next to each .dff)"
        )
        self._radio_single.setChecked(True)

        self._btn_group = QButtonGroup(self)
        self._btn_group.addButton(self._radio_single)
        self._btn_group.addButton(self._radio_per)
        self._btn_group.buttonClicked.connect(self._on_mode_toggled)

        # --- Single-root path row ---
        root_layout = QHBoxLayout()
        self._edit_root = QLineEdit()
        self._edit_root.setPlaceholderText(
            "/home/user/music_export"
        )
        self._edit_root.textChanged.connect(self._emit_mode_changed)

        self._btn_browse_root = QPushButton("Browse...")
        self._btn_browse_root.clicked.connect(self._on_browse_root)

        root_layout.addWidget(QLabel("Output root:"))
        root_layout.addWidget(self._edit_root, 1)
        root_layout.addWidget(self._btn_browse_root)

        layout.addWidget(self._radio_single)
        layout.addLayout(root_layout)
        layout.addWidget(self._radio_per)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def _on_mode_toggled(self) -> None:
        single = self._radio_single.isChecked()
        self._edit_root.setEnabled(single)
        self._btn_browse_root.setEnabled(single)
        self._emit_mode_changed()

    @Slot()
    def _on_browse_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Root Directory",
            str(Path.home()),
        )
        if folder:
            self._edit_root.setText(folder)

    @Slot(str)
    def _emit_mode_changed(self, _text: str = "") -> None:
        self.mode_changed.emit(self.output_mode(), self.output_root())


