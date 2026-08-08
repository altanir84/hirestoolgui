"""
File-tree panel with checkboxes, add/remove folder controls, and
drag-and-drop support.

Displays the hierarchical view of scanned DFF files and allows the user
to select which files will be converted.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, Slot, QSettings, QModelIndex
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QStandardItem
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from app.core.file_scanner import FileScanner
from app.models.file_tree_model import FileTreeModel
from app.models.file_node import FileNode, CheckState


class FilePanel(QWidget):
    """
    Panel containing the tree view, action buttons, and drag-drop zone.

    Signals
    -------
    scan_completed(total_files):
        Emitted after a successful scan with the total number of DFF
        files discovered.
    selection_changed(checked_count):
        Emitted whenever the user toggles a checkbox.  *checked_count*
        is the number of FILE nodes currently CHECKED.
    """

    scan_completed = Signal(int)
    selection_changed = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = FileTreeModel(self)
        self._warning_callback = None  # set by MainWindow
        self._root_folders: List[Path] = []
        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_warning_callback(self, callback) -> None:
        """Register a callable ``(msg: str) -> None`` for scan warnings."""
        self._warning_callback = callback

    def add_folder(self, folder: Path) -> None:
        """
        Add *folder* to the list of roots, avoiding nested duplicates.

        - If *folder* is a descendant of an existing root, ignore it.
        - If *folder* is an ancestor of existing roots, replace them.
        """
        folder = folder.resolve()

        # Ignore if already covered by an existing root.
        for existing in self._root_folders:
            try:
                folder.relative_to(existing)
                return  # folder is inside an existing root
            except ValueError:
                pass

        # Remove any existing roots that are inside the new folder.
        self._root_folders = [
            r for r in self._root_folders
            if not self._is_inside(r, folder)
        ]

        self._root_folders.append(folder)
        self._rescan()

    def checked_files(self) -> List[Path]:
        """Return absolute paths of all CHECKED FILE nodes."""
        return self._model.checked_files()

    def has_files(self) -> bool:
        """``True`` if the model contains at least one FILE node."""
        root = self._model.root_node()
        return root is not None and root.total_file_count > 0

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # -- Toolbar --
        toolbar = QHBoxLayout()

        self._btn_add = QPushButton("Add Folder...")
        self._btn_add.setToolTip("Add a root folder to scan for .dff files")

        self._btn_remove = QPushButton("Remove Selected")
        self._btn_remove.setToolTip(
            "Remove the selected root folder and its subtree"
        )
        self._btn_remove.setEnabled(False)

        self._btn_select_all = QPushButton("Select All")
        self._btn_deselect_all = QPushButton("Deselect All")

        toolbar.addWidget(self._btn_add)
        toolbar.addWidget(self._btn_remove)
        toolbar.addStretch()
        toolbar.addWidget(self._btn_select_all)
        toolbar.addWidget(self._btn_deselect_all)

        # -- Tree view --
        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setHeaderHidden(False)
        self._tree.header().setStretchLastSection(True)
        self._tree.header().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self._tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._tree.setDragEnabled(False)
        self._tree.setAcceptDrops(True)
        self._tree.setDropIndicatorShown(True)
        self._tree.setDragDropMode(QAbstractItemView.DropOnly)
        self._tree.dragEnterEvent = self._on_drag_enter
        self._tree.dropEvent = self._on_drop

        # -- Status label --
        self._lbl_status = QLabel("No folders added yet.")
        self._lbl_status.setStyleSheet("color: #888; padding: 4px;")

        layout.addLayout(toolbar)
        layout.addWidget(self._tree)
        layout.addWidget(self._lbl_status)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._btn_add.clicked.connect(self._on_add_folder)
        self._btn_remove.clicked.connect(self._on_remove_folder)
        self._btn_select_all.clicked.connect(self._on_select_all)
        self._btn_deselect_all.clicked.connect(self._on_deselect_all)
        self._model.checked_files_changed.connect(self._on_checked_changed)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def _on_add_folder(self) -> None:
        """Open a folder dialog, defaulting to the last-used directory."""
        from PySide6.QtWidgets import QFileDialog  # noqa: WPS433

        settings = QSettings()
        last_dir = settings.value("last_folder", str(Path.home()))

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Root Folder",
            last_dir,
        )
        if folder:
            settings.setValue("last_folder", folder)
            self.add_folder(Path(folder))

    @Slot()
    def _on_remove_folder(self) -> None:
        """Remove the selected top-level folder(s) from the tree."""
        indexes = self._tree.selectionModel().selectedRows()
        if not indexes:
            return

        # Collect rows to remove (sorted descending to preserve indices).
        rows = sorted({idx.row() for idx in indexes}, reverse=True)
        for row in rows:
            if row < len(self._root_folders):
                del self._root_folders[row]
        self._rescan()

    @Slot()
    def _on_select_all(self) -> None:
        if self._model.rowCount() == 0:
            return
        self._set_tree_state(True)

    @Slot()
    def _on_deselect_all(self) -> None:
        if self._model.rowCount() == 0:
            return
        self._set_tree_state(False)

    @Slot()
    def _on_checked_changed(self) -> None:
        count = len(self._model.checked_files())
        self.selection_changed.emit(count)

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------

    def _on_drag_enter(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _on_drop(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                self.add_folder(path)
        event.acceptProposedAction()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rescan(self) -> None:
        """Re-run the scanner and refresh the model."""
        scanner = FileScanner(self._root_folders, self._warning_callback)
        new_root = scanner.scan()
        self._model.set_root_node(new_root)
        self._tree.expandAll()

        total = new_root.total_file_count

        self._lbl_status.setText(
            f"{total} DFF file(s) across "
            f"{len(self._root_folders)} folder(s)"
        )
        self._btn_remove.setEnabled(len(self._root_folders) > 0)
        self.scan_completed.emit(total)

    def _set_tree_state(self, checked: bool) -> None:
        """
        Recursively check or uncheck every item in the tree.

        Blocks the model's ``itemChanged`` signal during the bulk
        update to avoid feedback loops, then emits
        ``checked_files_changed`` once.
        """
        file_state = CheckState.CHECKED if checked else CheckState.UNCHECKED
        root_node = self._model.root_node()

        if root_node is not None:
            root_node.set_check_state(file_state)

        qt_state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        
        root = self._model.invisibleRootItem()

        self._model._updating = True
        self._apply_state_recursive(root, qt_state)
        self._model._updating = False
        self._model.checked_files_changed.emit()

    def _apply_state_recursive(
        self, parent: QStandardItem, state: Qt.CheckState
    ) -> None:
        """Recursively apply *state* to *parent* and all descendants."""
        parent.setCheckState(state)
        for row in range(parent.rowCount()):
            self._apply_state_recursive(parent.child(row), state)

    @staticmethod
    def _is_inside(child: Path, parent: Path) -> bool:
        """Return ``True`` if *child* is a descendant of *parent*."""
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False


