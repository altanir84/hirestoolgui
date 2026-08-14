"""
Tag editor dialog for DFF files missing minimum metadata.

Allows the user to review and edit artist, album, and per-track
information inferred from the folder structure before conversion.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.structure_analyzer import AlbumInfo, TrackInfo


class TagEditorDialog(QDialog):
    """
    Modal dialog for reviewing and editing inferred tags.

    Parameters
    ----------
    album_info:
        Pre-filled :class:`AlbumInfo` from :class:`StructureAnalyzer`.
    parent:
        Parent widget.
    """

    def __init__(
        self,
        album_info: AlbumInfo,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._album_info = album_info
        self.setWindowTitle("Edit Tags — Missing Metadata")
        self.setMinimumSize(550, 400)
        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_album_info(self) -> AlbumInfo:
        """Return the (possibly edited) :class:`AlbumInfo`."""
        self._album_info.artist = self._edit_artist.text().strip()
        self._album_info.album = self._edit_album.text().strip()

        for row in range(self._table.rowCount()):
            track = self._album_info.tracks[row]
            number_item = self._table.item(row, 0)
            title_item = self._table.item(row, 1)
            if number_item is not None:
                try:
                    track.track_number = int(number_item.text().strip())
                except ValueError:
                    pass
            if title_item is not None:
                track.track_title = title_item.text().strip()

        return self._album_info

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # -- Artist / Album row --
        form = QFormLayout()
        self._edit_artist = QLineEdit()
        self._edit_album = QLineEdit()
        form.addRow("Artist:", self._edit_artist)
        form.addRow("Album:", self._edit_album)
        layout.addLayout(form)

        # -- Disc label (read-only) --
        if self._album_info.disc:
            disc_label = QLabel(f"Disc: {self._album_info.disc}")
            disc_label.setStyleSheet("color: #888;")
            layout.addWidget(disc_label)

        # -- Track table --
        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Track #", "Title"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self._table.setSelectionMode(QTableWidget.NoSelection)
        layout.addWidget(self._table, 1)

        # -- OK button --
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Populate
    # ------------------------------------------------------------------

    def _populate(self) -> None:
        """Fill the form and table with inferred data."""
        self._edit_artist.setText(self._album_info.artist)
        self._edit_album.setText(self._album_info.album)

        self._table.setRowCount(len(self._album_info.tracks))
        for row, track in enumerate(self._album_info.tracks):
            number_item = QTableWidgetItem(str(track.track_number))
            number_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 0, number_item)

            title_item = QTableWidgetItem(track.track_title)
            self._table.setItem(row, 1, title_item)


