"""
Recursive filesystem scanner that builds a :class:`FileNode` tree.

Only ``.dff``, ``.DFF``, ``.iso`` and ``.ISO`` files are collected.
The resulting tree is ready to be consumed by :class:`FileTreeModel`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from app.models.file_node import FileNode, NodeType, CheckState


class FileScanner:
    """
    Walk one or more root directories and construct a :class:`FileNode`
    hierarchy containing every ``.dff`` / ``.DFF`` and ``.iso`` / ``.ISO``
    file found.

    Parameters
    ----------
    roots:
        List of absolute paths to scan.  Non-existent paths are skipped
        with a warning emitted via *warning_callback*.
    warning_callback:
        Optional callable ``(message: str) -> None`` invoked for every
        non-fatal issue encountered (e.g. permission errors, broken
        symlinks).
    """

    def __init__(
        self,
        roots: List[Path],
        warning_callback: Optional[callable] = None,
    ) -> None:
        self._roots = roots
        self._warning = warning_callback or (lambda _: None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> FileNode:
        """
        Execute the full scan and return the root :class:`FileNode`.

        The returned node is a virtual ROOT whose children are the
        top-level directories supplied to the constructor.
        """
        root_node = FileNode("root", Path("."), NodeType.ROOT)

        for folder in self._roots:
            if not folder.is_dir():
                self._warning(f"Skipping non-existent folder: {folder}")
                continue
            dir_node = self._walk(folder)
            if dir_node is not None:
                root_node.append_child(dir_node)

        root_node.total_file_count = sum(
            c.total_file_count for c in root_node.children
        )
        root_node.total_dff_count = sum(
            c.total_dff_count for c in root_node.children
        )
        root_node.total_iso_count = sum(
            c.total_iso_count for c in root_node.children
        )
        return root_node

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _walk(self, directory: Path) -> Optional[FileNode]:
        """
        Recursively scan *directory*, returning a :class:`FileNode`.

        Returns ``None`` if the directory is inaccessible or contains no
        DFF or ISO files (empty subtrees are pruned).
        """
        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except OSError as exc:
            self._warning(f"Cannot read {directory}: {exc}")
            return None

        dir_node = FileNode(directory.name, directory, NodeType.DIRECTORY)
        file_count = 0

        for entry in entries:
            if entry.is_symlink():
                try:
                    target = entry.resolve(strict=True)
                except OSError:
                    self._warning(f"Broken symlink skipped: {entry}")
                    continue
                if target.is_dir():
                    child = self._walk(target)
                    if child is not None:
                        child.name = entry.name
                        child.path = entry
                        dir_node.append_child(child)
                        file_count += child.total_file_count
                elif self._is_dff(target):
                    file_node = FileNode(entry.name, entry, NodeType.FILE)
                    file_node.total_file_count = 1
                    file_node.total_dff_count = 1
                    dir_node.append_child(file_node)
                    file_count += 1
                elif self._is_iso(target):
                    file_node = FileNode(entry.name, entry, NodeType.ISO)
                    file_node.total_file_count = 1
                    file_node.total_iso_count = 1
                    dir_node.append_child(file_node)
                    file_count += 1
                continue

            if entry.is_dir():
                child = self._walk(entry)
                if child is not None:
                    dir_node.append_child(child)
                    file_count += child.total_file_count
            elif self._is_dff(entry):
                file_node = FileNode(entry.name, entry, NodeType.FILE)
                file_node.total_file_count = 1
                file_node.total_dff_count = 1
                dir_node.append_child(file_node)
                file_count += 1
            elif self._is_iso(entry):
                file_node = FileNode(entry.name, entry, NodeType.ISO)
                file_node.total_file_count = 1
                file_node.total_iso_count = 1
                dir_node.append_child(file_node)
                file_count += 1

        if file_count == 0:
            return None

        dir_node.total_file_count = file_count

        dir_node.total_dff_count = sum(
            c.total_dff_count for c in dir_node.children
        )
        dir_node.total_iso_count = sum(
            c.total_iso_count for c in dir_node.children
        )

        dir_node.total_file_count = file_count

        return dir_node


    @staticmethod
    def _is_dff(path: Path) -> bool:
        """Return ``True`` if *path* has a ``.dff`` / ``.DFF`` suffix."""
        return path.suffix.lower() == ".dff"


    @staticmethod
    def _is_iso(path: Path) -> bool:
        """Return ``True`` if *path* has a ``.iso`` / ``.ISO`` suffix."""
        return path.suffix.lower() == ".iso"



