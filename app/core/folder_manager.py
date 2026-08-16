"""
Folder manager for HiResToolsGUI.

Manages the lists of root folders, tree exclusions, and user exclusions
used by the file panel to control what is scanned and displayed.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set

from app.models.file_node import FileNode, NodeType


class FolderManager:
    """
    Manages folder state for the file tree.

    Parameters
    ----------
    warning_callback:
        Optional callable invoked for non-fatal issues.
    """

    def __init__(self, warning_callback: Optional[callable] = None) -> None:
        self._warning = warning_callback or (lambda _: None)
        self._root_folders: List[Path] = []
        self._tree_exclude: Set[Path] = set()
        self._user_excluded: Set[Path] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def root_folders(self) -> List[Path]:
        """Return a copy of the current root folders list."""
        return list(self._root_folders)

    @property
    def tree_exclude(self) -> Set[Path]:
        """Return the set of automatically excluded paths."""
        return self._tree_exclude

    @property
    def user_excluded(self) -> Set[Path]:
        """Return the set of user-excluded paths."""
        return self._user_excluded

    @property
    def refresh_exclude(self) -> Set[Path]:
        """Return the combined exclusion set for Refresh Tree."""
        return self._tree_exclude | self._user_excluded

    def has_roots(self) -> bool:
        """Return ``True`` if any root folders are registered."""
        return len(self._root_folders) > 0

    def add_folder(self, folder: Path) -> bool:
        """
        Add *folder* to the list of roots, avoiding nested duplicates.

        - If *folder* is a descendant of an existing root, ignore it.
        - If *folder* is an ancestor of existing roots, replace them.

        Returns ``True`` if the folder was added.
        """
        folder = folder.resolve()

        for existing in self._root_folders:
            try:
                folder.relative_to(existing)
                return False
            except ValueError:
                pass

        self._root_folders = [
            r for r in self._root_folders
            if not self._is_inside(r, folder)
        ]
        self._root_folders.append(folder)
        return True

    def remove_root(self, path: Path) -> None:
        """Remove *path* from root folders if present."""
        if path in self._root_folders:
            self._root_folders.remove(path)

    def add_user_excluded(self, path: Path) -> None:
        """Add *path* to the user-excluded set."""
        self._user_excluded.add(path)

    def clear_all(self) -> None:
        """Clear all folder state."""
        self._root_folders.clear()
        self._tree_exclude.clear()
        self._user_excluded.clear()

    def rebuild_exclusions(self, new_root: FileNode) -> None:
        """
        Rebuild the tree-exclusion set from a freshly scanned tree.

        Parameters
        ----------
        new_root:
            The root node produced by a completed scan.
        """
        tree_paths: Set[Path] = set()
        self._collect_tree_paths(new_root, tree_paths)

        self._tree_exclude.clear()
        for folder in self._root_folders:
            self._collect_excluded(folder, tree_paths, self._tree_exclude)

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_inside(child: Path, parent: Path) -> bool:
        """Return ``True`` if *child* is a descendant of *parent*."""
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Tree path collection
    # ------------------------------------------------------------------

    def _collect_tree_paths(
        self, node: FileNode, result: Set[Path]
    ) -> None:
        """
        Recursively collect paths of all directories that are part of
        the tree view.
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



