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
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QStandardItem
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

from app.core.folder_manager import FolderManager
from app.core.scan_orchestrator import ScanOrchestrator
from app.core.structure_analyzer import StructureAnalyzer
from app.models.file_tree_model import FileTreeModel
from app.models.file_node import CheckState, FileNode, NodeType
from app.widgets.folder_dialog import FolderDialog


class FilePanel(QWidget):
    """
    Panel containing the tree view, action buttons, and drag-drop zone.

    Signals
    -------
    scan_completed(total_files):
        Emitted after a successful scan with the total number of DFF
        and ISO files discovered.
    selection_changed(checked_count):
        Emitted whenever the user toggles a checkbox.
    scan_started():
        Emitted when a background scan begins.
    scan_finished():
        Emitted when a background scan ends.
    """

    scan_completed = Signal(int)
    selection_changed = Signal(int)
    scan_started = Signal()
    scan_finished = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = FileTreeModel(self)
        self._folders = FolderManager()
        self._scanner = ScanOrchestrator()
        self._warning_callback = None
        self.setAcceptDrops(True)
        self._build_ui()
        self._connect_signals()
        self._update_menu_states()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_warning_callback(self, callback) -> None:
        """Register a callable for scan warnings."""
        self._warning_callback = callback
        self._scanner._warning = callback or (lambda _: None)
        self._folders._warning = callback or (lambda _: None)

    def is_scanning(self) -> bool:
        """Return ``True`` when a background scan is in progress."""
        return self._scanner.is_scanning

    def cancel_scan(self) -> None:
        """Request cancellation of the running background scan."""
        self._scanner.cancel()

    def add_folder(self, folder: Path) -> None:
        """Add *folder* to the list of roots and rescan."""
        if self._folders.add_folder(folder):
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

        # Folders dropdown.
        self._btn_folders = QPushButton("Folders")
        self._menu_folders = QMenu(self)
        self._btn_folders.setMenu(self._menu_folders)

        self._act_add = QAction("Add Folder...", self)
        self._act_add.triggered.connect(self._on_add_folder)
        self._menu_folders.addAction(self._act_add)

        self._act_add_multiple = QAction("Add Multiple...", self)
        self._act_add_multiple.triggered.connect(
            self._on_add_multiple_folders
        )
        self._menu_folders.addAction(self._act_add_multiple)

        self._menu_folders.addSeparator()

        self._act_rescan = QAction("Rescan Folders", self)
        self._act_rescan.triggered.connect(self._rescan_folders)
        self._menu_folders.addAction(self._act_rescan)

        self._act_reset = QAction("Reset Folders", self)
        self._act_reset.triggered.connect(self._clear_all)
        self._menu_folders.addAction(self._act_reset)

        self._menu_folders.addSeparator()

        self._act_remove = QAction("Remove Selected", self)
        self._act_remove.triggered.connect(self._on_remove_folder)
        self._menu_folders.addAction(self._act_remove)

        # Select dropdown.
        self._btn_select = QPushButton("Select")
        self._btn_select.setEnabled(False)
        self._menu_select = QMenu(self)
        self._btn_select.setMenu(self._menu_select)

        self._act_select_all = QAction("Select All", self)
        self._act_select_all.triggered.connect(self._on_select_all)
        self._menu_select.addAction(self._act_select_all)

        self._act_deselect_all = QAction("Deselect All", self)
        self._act_deselect_all.triggered.connect(self._on_deselect_all)
        self._menu_select.addAction(self._act_deselect_all)

        toolbar.addWidget(self._btn_folders)
        toolbar.addWidget(self._btn_select)
        toolbar.addStretch()

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

        # -- Status bar --
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
        self._model.checked_files_changed.connect(
            self._on_checked_changed
        )
        self._scanner.scan_started.connect(self._on_scan_started)
        self._scanner.scan_finished.connect(self._on_scan_finished)

    # ------------------------------------------------------------------
    # Menu state management
    # ------------------------------------------------------------------

    def _update_menu_states(self) -> None:
        """Update enabled state of all menu actions."""
        has_roots = self._folders.has_roots()
        has_items = self.has_files()

        self._act_rescan.setEnabled(has_roots)
        self._act_reset.setEnabled(has_roots)
        self._act_remove.setEnabled(has_roots)
        self._btn_select.setEnabled(has_items)
        self._act_select_all.setEnabled(has_items)
        self._act_deselect_all.setEnabled(has_items)

    # ------------------------------------------------------------------
    # Slots – folder actions
    # ------------------------------------------------------------------

    @Slot()
    def _on_add_folder(self) -> None:
        """Open a folder dialog and add the selected folder."""
        settings = QSettings()
        last_dir = settings.value("last_folder", str(Path.home()))

        folder = QFileDialog.getExistingDirectory(
            self, "Select Root Folder", last_dir,
        )
        if folder:
            settings.setValue("last_folder", folder)
            self.add_folder(Path(folder))

    @Slot()
    def _on_add_multiple_folders(self) -> None:
        """Open the Add Multiple dialog and add selected folders."""
        paths = FolderDialog.select_folders(self)
        for path in paths:
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
            if tr in self._folders.root_folders:
                self._folders.remove_root(tr)
            else:
                self._folders.add_user_excluded(tr)
            self._model.remove_by_path(tr)

        if not self.has_files():
            self._clear_all()
            return

        new_root = self._model.root_node()
        self._update_status_label(new_root)
        self._update_menu_states()
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

    # ------------------------------------------------------------------
    # Slots – selection
    # ------------------------------------------------------------------

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
        self._folders.clear_all()
        empty_root = FileNode("root", Path("."), NodeType.ROOT)
        self._model.set_root_node(empty_root)
        self._update_status_label(None)
        self._lbl_selected.setText("")
        self._update_menu_states()
        self.scan_completed.emit(0)
        self._on_checked_changed()

    # ------------------------------------------------------------------
    # Drag and drop
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
        """Re-scan only the folders currently shown in the tree view."""
        if not self._folders.has_roots():
            return

        self._start_scan(
            self._folders.root_folders,
            "Refreshing tree...",
            exclude_folders=self._folders.refresh_exclude,
        )

    def _rescan_folders(self) -> None:
        """Re-scan all imported root folders."""
        if not self._folders.has_roots():
            return

        self._start_scan(
            self._folders.root_folders, "Rescanning folders..."
        )

    def _start_scan(
        self,
        folders: List[Path],
        label: str,
        exclude_folders: Optional[set] = None,
    ) -> None:
        """Launch a background scan."""
        self._lbl_status.setText(label)
        self._lbl_status.setStyleSheet("color: #f39c12; padding: 4px;")
        self._set_buttons_enabled(False)
        self._scanner.start_scan(
            folders,
            progress_callback=self._on_scan_progress,
            exclude_folders=exclude_folders,
        )

    # ------------------------------------------------------------------
    # Scan lifecycle slots
    # ------------------------------------------------------------------

    @Slot()
    def _on_scan_started(self) -> None:
        """Forward scan_started signal."""
        self.scan_started.emit()

    @Slot(object)
    def _on_scan_finished(self, new_root: FileNode) -> None:
        """Populate the tree with scan results and finalise UI state."""
        self._folders.rebuild_exclusions(new_root)

        self._model.set_root_node(new_root)
        self._tree.expandAll()

        self._set_buttons_enabled(True)

        total = new_root.total_dff_count + new_root.total_iso_count

        self._update_status_label(new_root, False)
        self._update_menu_states()

        self.scan_completed.emit(total)
        self._on_checked_changed()
        self.scan_finished.emit()

    # ------------------------------------------------------------------
    # Button state
    # ------------------------------------------------------------------

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable toolbar buttons during scan."""
        self._btn_folders.setEnabled(enabled)
        self._btn_select.setEnabled(enabled)
        if not enabled:
            self._act_remove.setEnabled(False)
            self._act_rescan.setEnabled(False)
            self._act_reset.setEnabled(False)
            self._act_select_all.setEnabled(False)
            self._act_deselect_all.setEnabled(False)

    def _set_tree_state(self, checked: bool) -> None:
        """Recursively check or uncheck every item in the tree."""
        file_state = (
            CheckState.CHECKED if checked else CheckState.UNCHECKED
        )
        root_node = self._model.root_node()

        if root_node is not None:
            root_node.set_check_state(file_state)

        qt_state = (
            Qt.CheckState.Checked
            if checked
            else Qt.CheckState.Unchecked
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

    def _on_scan_progress(self, directory: Path) -> None:
        """Update status label during scan."""
        display = StructureAnalyzer.relative_path(
            directory, self._folders.root_folders
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
            if not self._folders.has_roots():
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
        root_count = len(self._folders.root_folders)
        if iso_count > 0:
            status = (
                f"{total_dff} DFF + {iso_count} ISO file(s) across "
                f"{root_count} folder(s)"
            )
        else:
            status = (
                f"{total_dff} DFF file(s) across "
                f"{root_count} folder(s)"
            )
        if was_cancelled:
            status += " (scan cancelled)"
        self._lbl_status.setText(status)
        self._lbl_status.setStyleSheet(
            "color: #e74c3c; padding: 4px;"
            if was_cancelled
            else "color: #888; padding: 4px;"
        )



