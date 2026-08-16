"""
Data structures for the file-tree model.

Defines :class:`FileNode` — the fundamental building block used by
:class:`FileTreeModel` to represent the hierarchical structure of
directories and DFF files discovered by the scanner.
"""

from __future__ import annotations

from enum import Enum, auto
from pathlib import Path
from typing import List, Optional


class NodeType(Enum):
    """Kinds of node that may appear in the file tree."""
    ROOT = auto()
    DIRECTORY = auto()
    FILE = auto()
    ISO = auto()

    
class CheckState(Enum):
    """Tri-state checkbox values used in the tree view."""
    UNCHECKED = 0
    PARTIALLY_CHECKED = 1
    CHECKED = 2


class FileNode:
    """
    A single node in the file-tree model.

    A node may be:

    * **ROOT** — virtual top-level container (sentinel path ``Path(".")``).
    * **DIRECTORY** — a real folder on disk that may contain further
      directories and/or ``.dff`` / ``.DFF`` files.
    * **FILE** — a leaf node representing a ``.dff`` / ``.DFF`` file
      eligible for conversion.

    Parameters
    ----------
    name:
        Display name shown in the tree view (file or folder name).
    path:
        Absolute filesystem path.  For ``ROOT`` nodes this is a
        sentinel :class:`Path` pointing to ``"."``.
    node_type:
        One of :attr:`NodeType.ROOT`, :attr:`NodeType.DIRECTORY`, or
        :attr:`NodeType.FILE`.

    Attributes
    ----------
    parent:
        Back-reference to the parent :class:`FileNode`.  ``None`` for
        the ROOT node.
    children:
        Ordered list of child nodes.
    check_state:
        Current checkbox state.  Always updated via
        :meth:`set_check_state` so that parent states stay consistent.
    checked_file_count:
        Number of *FILE* descendants that are :attr:`CheckState.CHECKED`.
    total_file_count:
        Total number of *FILE* descendants, regardless of state.
    """

    __slots__ = (
        "name",
        "path",
        "node_type",
        "parent",
        "children",
        "check_state",
        "checked_file_count",
        "total_dff_count",
        "total_iso_count",
        "total_file_count",
    )

    def __init__(
        self,
        name: str,
        path: Path,
        node_type: NodeType,
        parent: Optional[FileNode] = None,
    ) -> None:
        self.name = name
        self.path = path
        self.node_type = node_type
        self.parent = parent
        self.children: List[FileNode] = []
        self.check_state = CheckState.UNCHECKED
        self.checked_file_count = 0
        self.total_dff_count = 0
        self.total_iso_count = 0
        self.total_file_count = 0

    # ------------------------------------------------------------------
    # Tree-structure helpers
    # ------------------------------------------------------------------

    def row(self) -> int:
        """Return the index of this node within its parent's children list."""
        if self.parent is None:
            return 0
        return self.parent.children.index(self)

    def append_child(self, child: FileNode) -> None:
        """Register *child* as a subordinate of this node."""
        child.parent = self
        self.children.append(child)

    def child(self, row: int) -> Optional[FileNode]:
        """Return the child at *row*, or ``None`` if out of bounds."""
        if 0 <= row < len(self.children):
            return self.children[row]
        return None

    def child_count(self) -> int:
        """Number of immediate children."""
        return len(self.children)

    def remove_child(self, child: FileNode) -> None:
        """
        Remove *child* from this node's children list and detach it.

        After removal, ancestor check-states and file counts are
        recalculated.
        """
        if child in self.children:
            self.children.remove(child)
            child.parent = None
            self._recompute_self()
            self._recompute_ancestors()

    # ------------------------------------------------------------------
    # Check-state propagation
    # ------------------------------------------------------------------

    def set_check_state(self, state: CheckState) -> None:
        """
        Apply a new check-state to this node and propagate the change.

        * **FILE nodes**: update themselves and recompute ancestors.
        * **DIRECTORY / ROOT nodes**: cascade the state to all FILE
          descendants, then recompute ancestors.
        """
        if self.node_type == NodeType.FILE:
            self._update_leaf_and_ancestors(state)
        else:
            self._cascade_to_descendants(state)
            self._recompute_ancestors()

    def _update_leaf_and_ancestors(self, state: CheckState) -> None:
        """Set *state* on a FILE node and walk up the tree."""
        self.check_state = state
        self.checked_file_count = 1 if state == CheckState.CHECKED else 0
        self._recompute_ancestors()

    def _cascade_to_descendants(self, state: CheckState) -> None:
        """
        Recursively push *state* to every FILE node below this directory.

        PARTIALLY_CHECKED is a derived value — it is never cascaded.
        """
        if state == CheckState.PARTIALLY_CHECKED:
            return

        self.check_state = state
        file_count = 0
        for child in self.children:
            if child.node_type == NodeType.FILE:
                child.check_state = state
                child.checked_file_count = (
                    1 if state == CheckState.CHECKED else 0
                )
                file_count += 1

            elif child.node_type == NodeType.ISO:
                child.check_state = state
                child.checked_file_count = (
                    1 if state == CheckState.CHECKED else 0
                )
                file_count += 1

            else:
                child._cascade_to_descendants(state)
                file_count += child.total_file_count

        self.checked_file_count = (
            file_count if state == CheckState.CHECKED else 0
        )

    def _recompute_self(self) -> None:
        """Recalculate this node's counts and check-state from children."""
        checked = 0
        total = 0
        dff = 0
        iso = 0
        for child in self.children:
            if child.node_type == NodeType.FILE:
                total += 1
                dff += 1
                if child.check_state == CheckState.CHECKED:
                    checked += 1
            elif child.node_type == NodeType.ISO:
                total += 1
                iso += 1
                if child.check_state == CheckState.CHECKED:
                    checked += 1
            else:
                total += child.total_file_count
                checked += child.checked_file_count
                dff += child.total_dff_count
                iso += child.total_iso_count

        self.total_file_count = total
        self.total_dff_count = dff
        self.total_iso_count = iso
        self.checked_file_count = checked

        if checked == 0:
            self.check_state = CheckState.UNCHECKED
        elif checked == total:
            self.check_state = CheckState.CHECKED
        else:
            self.check_state = CheckState.PARTIALLY_CHECKED

    def _recompute_ancestors(self) -> None:
        """Walk upward, recalculating parent check-states from children."""
        node = self.parent
        while node is not None:
            checked = 0
            total = 0
            for child in node.children:
                if child.node_type == NodeType.FILE:
                    total += 1
                    if child.check_state == CheckState.CHECKED:
                        checked += 1

                elif child.node_type == NodeType.ISO:
                    total += 1
                    if child.check_state == CheckState.CHECKED:
                        checked += 1

                else:
                    total += child.total_file_count
                    checked += child.checked_file_count

            dff = 0
            iso = 0
            for child in node.children:
                if child.node_type == NodeType.FILE:
                    dff += 1

                elif child.node_type == NodeType.ISO:
                    iso += 1

                else:
                    dff += child.total_dff_count
                    iso += child.total_iso_count

            node.total_dff_count = dff
            node.total_iso_count = iso
            node.total_file_count = total
            node.checked_file_count = checked

            if checked == 0:
                node.check_state = CheckState.UNCHECKED
            elif checked == total:
                node.check_state = CheckState.CHECKED
            else:
                node.check_state = CheckState.PARTIALLY_CHECKED

            node = node.parent

    # ------------------------------------------------------------------
    # Convenience queries
    # ------------------------------------------------------------------

    def is_file(self) -> bool:
        """``True`` if this node represents a ``.dff`` file."""
        return self.node_type == NodeType.FILE

    def is_directory(self) -> bool:
        """``True`` if this node represents a folder."""
        return self.node_type == NodeType.DIRECTORY

    def is_iso(self) -> bool:
        """``True`` if this node represents an ``.iso`` file."""
        return self.node_type == NodeType.ISO


