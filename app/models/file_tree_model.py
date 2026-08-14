"""
:class:`QStandardItemModel` subclass that backs the file-tree view.

Wraps a :class:`FileNode` tree produced by :class:`FileScanner` and
exposes it as a :class:`QStandardItemModel` for seamless integration
with :class:`QTreeView`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QStandardItem, QStandardItemModel

from app.models.file_node import CheckState, FileNode, NodeType


#: Custom Qt role used to store a back-reference to the original
#: :class:`FileNode` inside each :class:`QStandardItem`.
_FILE_NODE_ROLE = Qt.UserRole + 1


class FileTreeModel(QStandardItemModel):
    """
    Hierarchical model that mirrors a :class:`FileNode` tree using
    :class:`QStandardItem` nodes.

    Columns
    -------
    0
        Name (directory or file name).

    Signals
    -------
    checked_files_changed():
        Emitted whenever the set of CHECKED file items changes.
    """

    checked_files_changed = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.setHorizontalHeaderLabels(["Name"])
        self._root_node: Optional[FileNode] = None
        self._updating = False # guard flag
        self.itemChanged.connect(self._on_item_changed)

    # ------------------------------------------------------------------
    # Public mutators
    # ------------------------------------------------------------------

    def set_root_node(self, node: FileNode) -> None:
        """
        Replace the entire tree with a new root :class:`FileNode`.

        The existing model content is cleared and rebuilt from *node*.
        """
        self._root_node = node
        self.removeRows(0, self.rowCount())

        for i in range(node.child_count()):
            child = node.child(i)
            item = self._build_item(child)
            self.appendRow(item)

    def root_node(self) -> Optional[FileNode]:
        """Return the current root :class:`FileNode` (may be ``None``)."""
        return self._root_node

    def checked_files(self) -> List[Path]:
        """
        Return absolute paths of every FILE node whose associated
        :class:`QStandardItem` is currently checked.
        """
        result: List[Path] = []
        self._collect_checked(self.invisibleRootItem(), result)
        return result

    # ------------------------------------------------------------------
    # Helpers – tree construction
    # ------------------------------------------------------------------

    def _build_item(self, node: FileNode) -> QStandardItem:
        """
        Recursively convert a :class:`FileNode` subtree into a
        :class:`QStandardItem` tree.
        """
        item = QStandardItem(node.name)
        item.setData(node, _FILE_NODE_ROLE)
        item.setToolTip(str(node.path))

        if node.is_file():
            item.setCheckable(True)
            item.setCheckState(
                Qt.Checked if node.check_state == CheckState.CHECKED
                else Qt.Unchecked
            )
            item.setFlags(
                Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
            )
            item.setEditable(False)
        elif node.is_iso():
            item.setCheckable(True)
            item.setCheckState(
                Qt.Checked if node.check_state == CheckState.CHECKED
                else Qt.Unchecked
            )
            item.setFlags(
                Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
            )
            item.setEditable(False)
            item.setForeground(Qt.GlobalColor.cyan)
        else:
            # Directory: checkable, tri-state auto-handled by Qt.
            item.setCheckable(True)
            item.setCheckState(
                self._map_check_state(node.check_state)
            )
            item.setFlags(
                Qt.ItemIsEnabled | Qt.ItemIsSelectable
                | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate
            )
            item.setEditable(False)

            for i in range(node.child_count()):
                child_item = self._build_item(node.child(i))
                item.appendRow(child_item)

        return item

    # ------------------------------------------------------------------
    # Helpers – check-state sync
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QStandardItem) -> None:
        """
        Propagate a checkbox change from the Qt item back to the
        underlying :class:`FileNode` tree and emit
        :attr:`checked_files_changed`.
        """
        if self._updating:
            return
        
        node = item.data(_FILE_NODE_ROLE)
        if node is None:
            return

        self._updating = True

        new_state = (
            CheckState.CHECKED
            if item.checkState() == Qt.Checked
            else CheckState.UNCHECKED
        )
        node.set_check_state(new_state)

        # Sync Qt items with the updated FileNode tree.
        self._sync_item_states(self.invisibleRootItem())

        self._updating = False
        self.checked_files_changed.emit()

    def _sync_item_states(self, parent_item: QStandardItem) -> None:
        """
        Recursively walk the QStandardItem tree and align each item's
        ``Qt.CheckState`` with its underlying :class:`FileNode`.
        """
        for row in range(parent_item.rowCount()):
            item = parent_item.child(row)
            node = item.data(_FILE_NODE_ROLE)
            if node is None:
                continue

            expected = self._map_check_state(node.check_state)
            if item.checkState() != expected:
                item.setCheckState(expected)

            if item.hasChildren():
                self._sync_item_states(item)

    
    # ------------------------------------------------------------------
    # Helpers – traversal
    # ------------------------------------------------------------------

    def _collect_checked(
        self, parent: QStandardItem, result: List[Path]
    ) -> None:
        """Depth-first collection of checked file paths."""
        for row in range(parent.rowCount()):
            item = parent.child(row)
            node = item.data(_FILE_NODE_ROLE)
            if node is not None and (node.is_file() or node.is_iso()):
                if item.checkState() == Qt.Checked:
                    result.append(node.path)
            if item.hasChildren():
                self._collect_checked(item, result)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_check_state(state: CheckState) -> Qt.CheckState:
        """Map internal :class:`CheckState` to Qt's enum."""
        _map = {
            CheckState.UNCHECKED: Qt.Unchecked,
            CheckState.PARTIALLY_CHECKED: Qt.PartiallyChecked,
            CheckState.CHECKED: Qt.Checked,
        }
        return _map[state]



