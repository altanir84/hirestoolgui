"""
Folder selection dialog for HiResToolsGUI.

Provides a checkable directory tree for selecting multiple folders
at once.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTreeView,
    QVBoxLayout,
    QWidget,
)


class FolderDialog:
    """Static helper for the Add Multiple folders dialog."""

    @staticmethod
    def select_folders(parent: QWidget) -> List[Path]:
        """
        Open a dialog with a checkable directory tree for selecting
        multiple folders at once.

        Only ``/home`` and ``/mnt`` are shown as root entries.
        Defaults to the last visited folder.

        Returns a list of resolved paths, with ancestor/descendant
        conflicts resolved (children take precedence over parents).
        """
        settings = QSettings()
        last_dir = settings.value("last_folder", str(Path.home()))

        dlg = QDialog(parent)
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
                if (
                    first is not None
                    and first.data(Qt.UserRole) is None
                ):
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
                    [
                        e
                        for e in dir_path.iterdir()
                        if e.is_dir() and not e.name.startswith(".")
                    ],
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
                    to_expand = last_path.relative_to(
                        root_path
                    ).parts
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
            return []

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

        return resolved



