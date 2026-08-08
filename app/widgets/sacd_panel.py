"""
SACD extraction options panel.

Provides radio buttons for stereo/multi-channel selection, a CUE sheet
checkbox, and a drop-down for output format.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class SacdPanel(QGroupBox):
    """
    Group-box with SACD extraction options.

    Only enabled when at least one ``.iso`` file is checked in the
    file tree.

    Signals
    -------
    options_changed():
        Emitted whenever any option is toggled.
    """

    options_changed = Signal()

    OUTPUT_FORMATS = {
        "DSF (individual tracks)": "-s",
        "DSDIFF (individual tracks)": "-p",
        "DSDIFF Edit Master (single file)": "-e",
        "Raw ISO": "-I",
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("SACD Extraction Options", parent)
        self._build_ui()

    # ------------------------------------------------------------------
    # Public queries
    # ------------------------------------------------------------------

    def stereo(self) -> bool:
        """``True`` when stereo extraction is selected."""
        return self._radio_stereo.isChecked()

    def multichannel(self) -> bool:
        """``True`` when multi-channel extraction is selected."""
        return self._radio_multichannel.isChecked()

    def cue_sheet(self) -> bool:
        """``True`` when CUE sheet export is enabled."""
        return self._chk_cue.isChecked()

    def output_format_flag(self) -> str:
        """Return the CLI flag for the selected output format."""
        label = self._combo_format.currentText()
        return self.OUTPUT_FORMATS.get(label, "-s")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # -- Channel selection (radio buttons) --
        layout.addWidget(QLabel("Channel mode:"))

        self._radio_stereo = QRadioButton("Stereo (2ch)")
        self._radio_stereo.setChecked(True)
        self._radio_stereo.setToolTip("Extract stereo tracks")

        self._radio_multichannel = QRadioButton("Multi-channel (mch)")
        self._radio_multichannel.setToolTip("Extract multi-channel tracks")

        self._channel_group = QButtonGroup(self)
        self._channel_group.addButton(self._radio_stereo)
        self._channel_group.addButton(self._radio_multichannel)

        layout.addWidget(self._radio_stereo)
        layout.addWidget(self._radio_multichannel)

        # -- Output format (drop-down) --
        layout.addWidget(QLabel("Output format:"))
        self._combo_format = QComboBox()
        self._combo_format.addItems(self.OUTPUT_FORMATS.keys())
        self._combo_format.setCurrentIndex(0)  # DSF default
        layout.addWidget(self._combo_format)

        # -- CUE sheet --
        self._chk_cue = QCheckBox("Export CUE sheet")
        self._chk_cue.setChecked(False)
        self._chk_cue.setToolTip("Generate a CUE sheet describing the disc layout")
        layout.addWidget(self._chk_cue)

        layout.addStretch()

        # Wire signals.
        self._radio_stereo.toggled.connect(
            lambda _checked: self.options_changed.emit()
            )
        self._radio_multichannel.toggled.connect(
            lambda _checked: self.options_changed.emit()
            )
        self._combo_format.currentIndexChanged.connect(
            lambda _idx: self.options_changed.emit()
            )
        self._chk_cue.toggled.connect(
            lambda _checked: self.options_changed.emit()
            )



