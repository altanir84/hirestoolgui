"""
File-tree panel with checkboxes, add/remove folder controls, and
drag-and-drop support.

Displays the hierarchical view of scanned DFF and ISO files and allows
the user to select which files will be converted.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, Slot, QSettings
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QStandardItem
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QVBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeView,
    QWidget,
    QSizePolicy,
)

from app.core.file_scanner import FileScanner
from app.core.structure_analyzer import StructureAnalyzer
from app.models.file_tree_model import FileTreeModel
from app.models.file_node import CheckState


class FilePanel(QWidget):
    """
    Panel containing the tree view, action buttons, and drag-drop zone.

    Signals
    -------
    scan_completed(total_files):
        Emitted after a successful scan with the total number of DFF
        and ISO files discovered.
    selection_changed(checked_count):
        Emitted whenever the user toggles a checkbox.  *checked_count*
        is the number of FILE and ISO nodes currently CHECKED.
    """

    scan_completed = Signal(int)
    selection_changed = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = FileTreeModel(self)
        self._warning_callback = None  # set by MainWindow
        self._root_folders: List[Path] = []
        self.setAcceptDrops(True)
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

        for existing in self._root_folders:
            try:
                folder.relative_to(existing)
                return
            except ValueError:
                pass

        self._root_folders = [
            r for r in self._root_folders
            if not self._is_inside(r, folder)
        ]

        self._root_folders.append(folder)
        self._rescan()

    def checked_files(self) -> List[Path]:
        """Return absolute paths of all CHECKED FILE and ISO nodes."""
        return self._model.checked_files()

    def has_files(self) -> bool:
        """``True`` if the model contains at least one FILE or ISO node."""
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
        self._btn_add.setToolTip(
            "Add a root folder to scan for .dff and .iso files"
        )
        self._btn_add_multiple = QPushButton("Add Multiple...")
        self._btn_add_multiple.setToolTip(
            "Add multiple folders to scan for .dff and .iso files"
        )

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setToolTip("Re-scan all imported folders")

        self._btn_remove = QPushButton("Remove Selected")
        self._btn_remove.setToolTip(
            "Remove the selected root folder and its subtree"
        )
        self._btn_remove.setEnabled(False)

        self._btn_select_all = QPushButton("Select All")
        self._btn_deselect_all = QPushButton("Deselect All")

        toolbar.addWidget(self._btn_add)
        toolbar.addWidget(self._btn_add_multiple)
        toolbar.addWidget(self._btn_refresh)
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
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(
            self._on_context_menu
        )

        # -- Status bar (totals left, selected right) --
        status_row = QHBoxLayout()

        self._lbl_status = QLabel("No folders added yet.")
        self._lbl_status.setStyleSheet("color: #888; padding: 4px;")
        self._lbl_status.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred
        )
        self._lbl_status.setMinimumWidth(0)

        self._lbl_selected = QLabel("")
        self._lbl_selected.setStyleSheet("color: #888; padding: 4px;")
        self._lbl_selected.setAlignment(Qt.AlignRight)

        status_row.addWidget(self._lbl_status, 1)
        status_row.addWidget(self._lbl_selected)

        layout.addLayout(toolbar)
        layout.addWidget(self._tree)
        layout.addLayout(status_row)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._btn_add.clicked.connect(self._on_add_folder)
        self._btn_add_multiple.clicked.connect(
            self._on_add_multiple_folders
        )
        self._btn_refresh.clicked.connect(self._rescan)
        self._btn_remove.clicked.connect(self._on_remove_folder)
        self._btn_select_all.clicked.connect(self._on_select_all)
        self._btn_deselect_all.clicked.connect(self._on_deselect_all)
        self._model.checked_files_changed.connect(
            self._on_checked_changed
        )

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
    def _on_add_multiple_folders(self) -> None:
        """
        Open a dialog with a checkable directory tree for selecting
        multiple folders at once.  Only ``/home`` and ``/mnt`` are
        shown as root entries.  Defaults to the last visited folder.
        """
        from PySide6.QtWidgets import (
            QDialog, QDialogButtonBox, QVBoxLayout,
        )
        from PySide6.QtGui import QStandardItemModel, QStandardItem

        settings = QSettings()
        last_dir = settings.value("last_folder", str(Path.home()))

        dlg = QDialog(self)
        dlg.setWindowTitle("Select Multiple Folders")
        dlg.resize(650, 500)

        layout = QVBoxLayout(dlg)

        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["Name"])

        tree = QTreeView()
        tree.setModel(model)
        tree.setHeaderHidden(False)
        tree.header().setStretchLastSection(True)

        # Populate root level with only /home and /mnt.
        home_path = Path.home()
        mnt_path = Path("/mnt")

        for label, path in [("home", home_path), ("mnt", mnt_path)]:
            if path.exists():
                item = QStandardItem(label)
                item.setData(path, Qt.UserRole)
                item.setCheckable(True)
                item.setCheckState(Qt.Unchecked)
                dummy = QStandardItem("")
                dummy.setData(None, Qt.UserRole)
                item.appendRow(dummy)
                model.appendRow(item)

        # Lazy-load children when expanded.
        def _on_expanded(index):
            item = model.itemFromIndex(index)
            if item is None:
                return
            if item.rowCount() == 1:
                first = item.child(0)
                if first is not None and first.data(Qt.UserRole) is None:
                    pass
                else:
                    return
            elif item.rowCount() > 0:
                return

            item.removeRows(0, item.rowCount())
            dir_path = item.data(Qt.UserRole)
            if dir_path is None:
                return
            try:
                entries = sorted(
                    [e for e in dir_path.iterdir()
                     if e.is_dir() and not e.name.startswith(".")],
                    key=lambda p: p.name.lower(),
                )
                for entry in entries:
                    child = QStandardItem(entry.name)
                    child.setData(entry, Qt.UserRole)
                    child.setCheckable(True)
                    child.setCheckState(Qt.Unchecked)
                    dummy = QStandardItem("")
                    dummy.setData(None, Qt.UserRole)
                    child.appendRow(dummy)
                    item.appendRow(child)
            except OSError:
                pass

        tree.expanded.connect(_on_expanded)

        # Expand to last visited folder.
        last_path = Path(last_dir)

        def _expand_path(parent_item, parts):
            if not parts:
                return
            _on_expanded(model.indexFromItem(parent_item))
            for row in range(parent_item.rowCount()):
                child = parent_item.child(row)
                if child is not None and child.text() == parts[0]:
                    tree.expand(model.indexFromItem(child))
                    _expand_path(child, parts[1:])
                    return

        for row in range(model.rowCount()):
            root_item = model.item(row)
            root_path = root_item.data(Qt.UserRole)
            if root_path is not None:
                try:
                    last_path.relative_to(root_path)
                    to_expand = last_path.relative_to(root_path).parts
                    _expand_path(root_item, list(to_expand))
                    break
                except ValueError:
                    pass

        layout.addWidget(tree)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.Accepted:
            return

        # Collect checked directories.
        def _collect_checked(item):
            if item.checkState() == Qt.Checked:
                path = item.data(Qt.UserRole)
                if path is not None and path.is_dir():
                    self.add_folder(path)
            for row in range(item.rowCount()):
                _collect_checked(item.child(row))

        for row in range(model.rowCount()):
            _collect_checked(model.item(row))

    @Slot()
    def _on_remove_folder(self) -> None:
        """Remove root folders whose checkboxes are checked."""
        root = self._model.root_node()
        if root is None:
            return

        to_remove = []
        for i in range(root.child_count()):
            child = root.child(i)
            if child.check_state == CheckState.CHECKED:
                to_remove.append(child.path)

        if not to_remove:
            return

        self._root_folders = [
            f for f in self._root_folders if f not in to_remove
        ]
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
        checked = self._model.checked_files()
        count = len(checked)
        dff_count = sum(
            1 for f in checked if f.suffix.lower() == ".dff"
        )
        iso_count = sum(
            1 for f in checked if f.suffix.lower() == ".iso"
        )
        parts = []
        if dff_count:
            parts.append(f"{dff_count} DFF")
        if iso_count:
            parts.append(f"{iso_count} ISO")
        self._lbl_selected.setText(
            " + ".join(parts) + " selected" if parts else ""
        )
        self.selection_changed.emit(count)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _on_context_menu(self, pos) -> None:
        """Show a context menu for the tree view."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.addAction("Refresh", self._rescan)
        
        if self.has_files():
            menu.addAction("Expand All", self._tree.expandAll)
            menu.addAction("Collapse All", self._tree.collapseAll)
            menu.addSeparator()
            menu.addAction("Clear All", self._clear_all)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _clear_all(self) -> None:
        """Remove all root folders and clear the tree."""
        self._root_folders.clear()
        empty_root = FileScanner([], self._warning_callback).scan()
        self._model.set_root_node(empty_root)
        self._lbl_status.setText("No folders added yet.")
        self._lbl_status.setStyleSheet("color: #888; padding: 4px;")
        self._lbl_selected.setText("")
        self._btn_remove.setEnabled(False)
        self.scan_completed.emit(0)
        self._on_checked_changed()

    # ------------------------------------------------------------------
    # Drag and drop (on the FilePanel widget itself)
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
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
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self._lbl_status.setText("Scanning...")
        self._lbl_status.setStyleSheet("color: #f39c12; padding: 4px;")
        QApplication.processEvents()

        scanner = FileScanner(
            self._root_folders,
            self._warning_callback,
            progress_callback=self._on_scan_progress,
            )
        new_root = scanner.scan()
        self._model.set_root_node(new_root)
        self._tree.expandAll()

        QApplication.restoreOverrideCursor()

        total_dff = new_root.total_dff_count
        iso_count = new_root.total_iso_count
        total = total_dff + iso_count

        if total == 0 and len(self._root_folders) > 0:
            self._lbl_status.setText(
                "No DFF or ISO files found in the selected folder(s)."
            )
            self._lbl_status.setStyleSheet(
                "color: #e74c3c; padding: 4px;"
            )
        else:
            if iso_count > 0:
                status = (
                    f"{total_dff} DFF + {iso_count} ISO file(s) across "
                    f"{len(self._root_folders)} folder(s)"
                )
            else:
                status = (
                    f"{total_dff} DFF file(s) across "
                    f"{len(self._root_folders)} folder(s)"
                )
            self._lbl_status.setText(status)
            self._lbl_status.setStyleSheet("color: #888; padding: 4px;")

        self._btn_remove.setEnabled(len(self._root_folders) > 0)
        self.scan_completed.emit(total)
        self._on_checked_changed()

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

        qt_state = (
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
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

    def _on_scan_progress(self, directory: Path) -> None:
        """Update status label with the path relative to the root folder."""
        
        display = StructureAnalyzer.relative_path(
            directory, self._root_folders
        )
        self._lbl_status.setText(f"Scanning... {display}/")
        QApplication.processEvents()

