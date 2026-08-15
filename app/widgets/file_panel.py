"""
File-tree panel with checkboxes, add/remove folder controls, and
drag-and-drop support.

Displays the hierarchical view of scanned DFF and ISO files and allows
the user to select which files will be converted.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import List, Optional, Set

from PySide6.QtCore import Qt, Signal, Slot, QSettings, QThread
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QStandardItem
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QMenu,
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
from app.models.file_node import CheckState, FileNode, NodeType


class _ScanWorker(QThread):
    """
    Background worker that runs :meth:`FileScanner.scan` in a separate
    thread so the UI remains responsive during scanning.

    Signals
    -------
    scan_finished(root_node):
        Emitted when the scan completes (or is cancelled), carrying
        the resulting :class:`FileNode` tree.
    """

    scan_finished = Signal(object)

    def __init__(
        self,
        scanner: FileScanner,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Parameters
        ----------
        scanner:
            Pre-configured :class:`FileScanner` instance ready to run.
        parent:
            Optional parent QObject.
        """
        super().__init__(parent)
        self._scanner = scanner

    def run(self) -> None:
        """Execute the scan and emit the result."""
        root_node = self._scanner.scan()
        self.scan_finished.emit(root_node)


class FilePanel(QWidget):
    """
    Panel containing the tree view, action buttons, and drag-drop zone.

    Signals
    -------
    scan_completed(total_files):
        Emitted after a successful scan with the total number of DFF
        and ISO files discovered.
    selection_changed(checked_count):
        Emitted whenever the user toggles a checkbox. *checked_count*
        is the number of FILE and ISO nodes currently CHECKED.
    scan_started():
        Emitted when a background scan begins.
    scan_finished():
        Emitted when a background scan ends (completed or cancelled).
    """

    scan_completed = Signal(int)
    selection_changed = Signal(int)
    scan_started = Signal()
    scan_finished = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = FileTreeModel(self)
        self._warning_callback = None  # set by MainWindow
        self._root_folders: List[Path] = []
        self._tree_exclude: Set[Path] = set()
        self._user_excluded: Set[Path] = set()
        self._cancel_event: Optional[threading.Event] = None
        self._scan_worker: Optional[_ScanWorker] = None
        self._scanning = False
        self.setAcceptDrops(True)
        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_warning_callback(self, callback) -> None:
        """Register a callable ``(msg: str) -> None`` for scan warnings."""
        self._warning_callback = callback

    def is_scanning(self) -> bool:
        """Return ``True`` when a background scan is in progress."""
        return self._scanning

    def cancel_scan(self) -> None:
        """Request cancellation of the running background scan."""
        if self._cancel_event is not None:
            self._cancel_event.set()

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
        self._rescan_folders()

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

        self._btn_refresh_tree = QPushButton("Refresh Tree")
        self._btn_refresh_tree.setToolTip(
            "Re-scan only folders currently shown in the tree"
        )
        self._btn_refresh_tree.setEnabled(False)

        self._btn_rescan_folders = QPushButton("Rescan Folders")
        self._btn_rescan_folders.setToolTip(
            "Re-scan all imported folders for new or changed files"
        )
        self._btn_rescan_folders.setEnabled(False)

        self._btn_reset = QPushButton("Reset Folders")
        self._btn_reset.setToolTip(
            "Clear all imported folders and reset to initial state"
        )
        self._btn_reset.setEnabled(False)

        self._btn_remove = QPushButton("Remove Selected")
        self._btn_remove.setToolTip(
            "Remove the selected root folder and its subtree"
        )
        self._btn_remove.setEnabled(False)

        self._btn_select_all = QPushButton("Select All")
        self._btn_select_all.setEnabled(False)
        self._btn_deselect_all = QPushButton("Deselect All")
        self._btn_deselect_all.setEnabled(False)

        toolbar.addWidget(self._btn_add)
        toolbar.addWidget(self._btn_add_multiple)
        toolbar.addWidget(self._btn_refresh_tree)
        toolbar.addWidget(self._btn_rescan_folders)
        toolbar.addWidget(self._btn_reset)
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
        self._btn_refresh_tree.clicked.connect(self._refresh_tree)
        self._btn_rescan_folders.clicked.connect(self._rescan_folders)
        self._btn_reset.clicked.connect(self._clear_all)
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
        multiple folders at once. Only ``/home`` and ``/mnt`` are
        shown as root entries. Defaults to the last visited folder.
        """
        from PySide6.QtWidgets import (
            QDialog, QDialogButtonBox,
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

        # Collect all checked paths, then resolve ancestor/descendant
        # conflicts: if both a parent and its child are checked, only
        # the child is kept.
        def _is_inside(child: Path, parent: Path) -> bool:
            try:
                child.relative_to(parent)
                return True
            except ValueError:
                return False

        def _collect_checked_paths(item, paths):
            if item.checkState() == Qt.Checked:
                path = item.data(Qt.UserRole)
                if path is not None and path.is_dir():
                    paths.append(path)
            for row in range(item.rowCount()):
                _collect_checked_paths(item.child(row), paths)

        checked_paths: List[Path] = []
        for row in range(model.rowCount()):
            _collect_checked_paths(model.item(row), checked_paths)

        resolved: List[Path] = []
        for path in checked_paths:
            if any(
                other != path and _is_inside(other, path)
                for other in checked_paths
            ):
                continue
            resolved.append(path)

        for path in resolved:
            self.add_folder(path)

    @Slot()
    def _on_remove_folder(self) -> None:
        """Remove folders whose checkboxes are checked."""
        root = self._model.root_node()
        if root is None:
            return

        to_remove: List[Path] = []
        self._collect_checked_folders(root, to_remove)

        if not to_remove:
            return

        for tr in to_remove:
            if tr in self._root_folders:
                self._root_folders.remove(tr)
            else:
                self._user_excluded.add(tr)
            self._model.remove_by_path(tr)

        # If tree view has no files left, reset everything.
        if not self.has_files():
            self._clear_all()
            return

        new_root = self._model.root_node()
        self._update_status_label(new_root)
        self._on_checked_changed()

    def _collect_checked_folders(
        self, node: FileNode, result: List[Path]
    ) -> None:
        """Recursively collect paths of CHECKED directory nodes."""
        for i in range(node.child_count()):
            child = node.child(i)
            if child.node_type == NodeType.DIRECTORY:
                if child.check_state == CheckState.CHECKED:
                    result.append(child.path)
                self._collect_checked_folders(child, result)

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
        menu = QMenu(self)

        if self.has_files():
            menu.addAction("Refresh Tree", self._refresh_tree)
            menu.addAction("Expand All", self._tree.expandAll)
            menu.addAction("Collapse All", self._tree.collapseAll)

        menu.addAction("Rescan Folders", self._rescan_folders)

        if self.has_files():
            menu.addSeparator()
            menu.addAction("Clear All", self._clear_all)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _clear_all(self) -> None:
        """Remove all root folders and clear the tree."""
        self._root_folders.clear()
        self._tree_exclude.clear()
        self._user_excluded.clear()
        empty_root = FileScanner([], self._warning_callback).scan()
        self._model.set_root_node(empty_root)
        self._lbl_status.setText("No folders added yet.")
        self._lbl_status.setStyleSheet("color: #888; padding: 4px;")
        self._lbl_selected.setText("")
        self._btn_remove.setEnabled(False)
        self._btn_refresh_tree.setEnabled(False)
        self._btn_rescan_folders.setEnabled(False)
        self._btn_reset.setEnabled(False)
        self._btn_select_all.setEnabled(False)
        self._btn_deselect_all.setEnabled(False)
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
    # Scan operations
    # ------------------------------------------------------------------

    def _refresh_tree(self) -> None:
        """
        Re-scan only the folders currently visible in the tree view,
        skipping previously excluded subdirectories and user-removed
        folders.
        """
        if not self._root_folders:
            return

        self._start_scan(
            list(self._root_folders),
            "Refreshing tree...",
            exclude_folders=self._tree_exclude | self._user_excluded,
        )

    def _rescan_folders(self) -> None:
        """
        Re-scan all imported root folders, including those that did
        not previously contain any ``.dff`` or ``.iso`` files.

        Useful when the user has added new files to folders that were
        previously empty.
        """
        if not self._root_folders:
            return

        self._start_scan(list(self._root_folders), "Rescanning folders...")

    def _start_scan(
        self,
        folders: List[Path],
        label: str,
        exclude_folders: Optional[Set[Path]] = None,
    ) -> None:
        """
        Launch a background scan for *folders* and update the model
        on completion.

        If a scan is already running, it is cancelled first.

        Parameters
        ----------
        folders:
            List of absolute paths to scan.
        label:
            Status label text shown during the scan.
        exclude_folders:
            Optional set of paths to skip during the scan.
        """
        if self._scanning:
            self._cancel_scan_and_wait()

        self._scanning = True
        self._cancel_event = threading.Event()

        self._lbl_status.setText(label)
        self._lbl_status.setStyleSheet("color: #f39c12; padding: 4px;")

        self._set_buttons_enabled(False)
        self.scan_started.emit()

        scanner = FileScanner(
            folders,
            self._warning_callback,
            progress_callback=self._on_scan_progress,
            cancel_event=self._cancel_event,
            exclude_folders=exclude_folders,
        )

        self._scan_worker = _ScanWorker(scanner, self)
        self._scan_worker.scan_finished.connect(self._on_scan_finished)
        self._scan_worker.finished.connect(self._cleanup_worker)
        self._scan_worker.start()

    def _cancel_scan_and_wait(self) -> None:
        """
        Cancel the running scan and block until its worker has fully
        stopped, ensuring clean state before starting a new scan.
        """
        if self._cancel_event is not None:
            self._cancel_event.set()

        if self._scan_worker is not None and self._scan_worker.isRunning():
            self._scan_worker.quit()
            self._scan_worker.wait(5000)

        self._scanning = False
        self._cancel_event = None
        self._scan_worker = None

    @Slot()
    def _cleanup_worker(self) -> None:
        """Release the finished worker thread."""
        self._scan_worker = None

    @Slot(object)
    def _on_scan_finished(self, new_root: FileNode) -> None:
        """Populate the tree with scan results and finalise UI state."""
        was_cancelled = (
            self._cancel_event is not None
            and self._cancel_event.is_set()
        )

        self._scanning = False
        self._cancel_event = None

        # Compute which folders are in the tree view so we can
        # exclude everything else on the next Refresh Tree.
        tree_paths: Set[Path] = set()
        self._collect_tree_paths(new_root, tree_paths)

        self._tree_exclude.clear()
        for folder in self._root_folders:
            self._collect_excluded(folder, tree_paths, self._tree_exclude)

        self._model.set_root_node(new_root)
        self._tree.expandAll()

        self._set_buttons_enabled(True)

        total_dff = new_root.total_dff_count
        iso_count = new_root.total_iso_count
        total = total_dff + iso_count

        self._update_status_label(new_root, was_cancelled)

        has_items = self.has_files()
        self._btn_remove.setEnabled(len(self._root_folders) > 0)
        self._btn_refresh_tree.setEnabled(has_items)
        self._btn_rescan_folders.setEnabled(len(self._root_folders) > 0)
        self._btn_reset.setEnabled(len(self._root_folders) > 0)
        self._btn_select_all.setEnabled(has_items)
        self._btn_deselect_all.setEnabled(has_items)

        self.scan_completed.emit(total)
        self._on_checked_changed()
        self.scan_finished.emit()

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable toolbar buttons during scan."""
        self._btn_add.setEnabled(enabled)
        self._btn_add_multiple.setEnabled(enabled)
        self._btn_remove.setEnabled(
            enabled and len(self._root_folders) > 0
        )
        if enabled:
            has_items = self.has_files()
            self._btn_refresh_tree.setEnabled(has_items)
            self._btn_rescan_folders.setEnabled(
                len(self._root_folders) > 0
            )
            self._btn_reset.setEnabled(len(self._root_folders) > 0)
            self._btn_select_all.setEnabled(has_items)
            self._btn_deselect_all.setEnabled(has_items)
        else:
            self._btn_refresh_tree.setEnabled(False)
            self._btn_rescan_folders.setEnabled(False)
            self._btn_reset.setEnabled(False)
            self._btn_select_all.setEnabled(False)
            self._btn_deselect_all.setEnabled(False)

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

    # ------------------------------------------------------------------
    # Status label
    # ------------------------------------------------------------------

    def _update_status_label(
        self, node: Optional[FileNode], was_cancelled: bool = False
    ) -> None:
        """Update the status label with file counts from *node*."""
        if node is None or node.total_file_count == 0:
            if len(self._root_folders) == 0:
                self._lbl_status.setText("No folders added yet.")
                self._lbl_status.setStyleSheet(
                    "color: #888; padding: 4px;"
                )
            elif was_cancelled:
                self._lbl_status.setText("Folder scanning cancelled.")
                self._lbl_status.setStyleSheet(
                    "color: #e74c3c; padding: 4px;"
                )
            else:
                self._lbl_status.setText(
                    "No DFF or ISO files found in the selected folder(s)."
                )
                self._lbl_status.setStyleSheet(
                    "color: #e74c3c; padding: 4px;"
                )
            return

        total_dff = node.total_dff_count
        iso_count = node.total_iso_count
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
        if was_cancelled:
            status += " (scan cancelled)"
        self._lbl_status.setText(status)
        self._lbl_status.setStyleSheet(
            "color: #e74c3c; padding: 4px;"
            if was_cancelled
            else "color: #888; padding: 4px;"
        )

    # ------------------------------------------------------------------
    # Tree path collection for exclusion logic
    # ------------------------------------------------------------------

    def _collect_tree_paths(
        self, node: FileNode, result: Set[Path]
    ) -> None:
        """
        Recursively collect paths of all directories that are part of
        the tree view (i.e. contain or lead to ``.dff``/``.iso`` files).
        """
        for i in range(node.child_count()):
            child = node.child(i)
            if child.node_type in (NodeType.FILE, NodeType.ISO):
                if node.path is not None:
                    result.add(node.path)
                return
            if child.path is not None:
                result.add(child.path)
            self._collect_tree_paths(child, result)

    def _collect_excluded(
        self, directory: Path, tree_paths: Set[Path], result: Set[Path]
    ) -> None:
        """
        Recursively walk *directory* and add to *result* every
        subdirectory that has NO descendants in *tree_paths*.
        """
        try:
            for entry in directory.iterdir():
                if not entry.is_dir():
                    continue
                if any(
                    tp == entry or self._is_inside(tp, entry)
                    for tp in tree_paths
                ):
                    self._collect_excluded(entry, tree_paths, result)
                else:
                    result.add(entry)
        except OSError:
            pass



