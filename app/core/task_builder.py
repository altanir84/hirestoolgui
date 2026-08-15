"""
Conversion task builder for HiResToolsGUI.

Constructs :class:`ConversionTask` objects from a flat list of file
paths, handling both DFF and ISO sources with correct destination
path resolution.

When multiple ISOs exist in the same album folder, each is placed in
a ``DiscN`` sub-folder, with the number extracted from the filename
when possible.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from app.core.converter_worker import ConversionTask
from app.models.file_node import FileNode
from app.utils.logger import ErrorLogManager, LogManager
from app.widgets.output_panel import OutputPanel


class TaskBuilder:
    """
    Builds :class:`ConversionTask` objects for DFF and ISO files.

    DFF files use ``dff2dsf``; ISO files use ``sacd_extract``.
    Destination paths preserve the folder hierarchy exactly as shown
    in the tree view, using the root node of the file tree to
    determine the relative path for each checked file.
    """

    def __init__(
        self,
        log_manager: LogManager,
        error_log: ErrorLogManager,
    ) -> None:
        self._log_manager = log_manager
        self._error_log = error_log

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        files: List[Path],
        mode: str,
        output_root: Optional[Path],
        tree_root: Optional[FileNode] = None,
    ) -> List[ConversionTask]:
        """
        Convert a flat list of checked file paths into tasks.

        Parameters
        ----------
        files:
            Absolute paths of files to convert.
        mode:
            Output mode (``OutputPanel.MODE_SINGLE`` or per-folder).
        output_root:
            Destination root directory (single-root mode only).
        tree_root:
            Root node of the file tree, used to compute relative
            paths that preserve the tree-view hierarchy.
        """
        # Build a map from file path to its relative path within the
        # tree view.
        relative_map: Dict[Path, Path] = {}
        if tree_root is not None and mode == OutputPanel.MODE_SINGLE:
            self._build_relative_map(tree_root, Path(), relative_map)

        tasks: List[ConversionTask] = []

        for src in files:
            if src.suffix.lower() == ".iso":
                task = self._build_iso_task(
                    src, mode, output_root, relative_map,
                )
            else:
                task = self._build_dff_task(
                    src, mode, output_root, relative_map,
                )
            if task is not None:
                tasks.append(task)

        return tasks

    # ------------------------------------------------------------------
    # Per-type builders
    # ------------------------------------------------------------------

    def _build_iso_task(
        self,
        src: Path,
        mode: str,
        output_root: Optional[Path],
        relative_map: Dict[Path, Path],
    ) -> Optional[ConversionTask]:
        """Build a task for an ISO file, or ``None`` if skipped."""
        if mode == OutputPanel.MODE_SINGLE:
            rel = relative_map.get(src)
            if rel is None:
                self._log_manager.warning(
                    f"Skipping {src.name}: could not determine "
                    f"destination from tree view"
                )
                self._error_log.add_skipped(
                    str(src), "ISO",
                    "Could not determine destination from tree view",
                )
                return None

            dest_dir = output_root / rel.parent

            # Detect multiple ISOs in the same source album folder.
            iso_siblings = sorted(
                [p for p in src.parent.iterdir()
                 if p.suffix.lower() == ".iso"],
                key=lambda p: p.name.lower(),
            )
            if len(iso_siblings) > 1:
                disc_num = self._extract_disc_number(src.stem)
                if disc_num is not None:
                    disc_name = f"Disc{disc_num}"
                else:
                    idx = iso_siblings.index(src)
                    disc_name = f"Disc{idx + 1}"
                dest_dir = dest_dir / disc_name

            dest = dest_dir / (src.stem + ".dsf")
        else:
            dest_dir = src.parent / "converted"
            dest = dest_dir / (src.stem + ".dsf")

        return ConversionTask(
            source=src, destination=dest, converter="sacd_extract",
        )

    def _build_dff_task(
        self,
        src: Path,
        mode: str,
        output_root: Optional[Path],
        relative_map: Dict[Path, Path],
    ) -> Optional[ConversionTask]:
        """Build a task for a DFF file, or ``None`` if skipped."""
        if mode == OutputPanel.MODE_SINGLE:
            rel = relative_map.get(src)
            if rel is None:
                self._log_manager.warning(
                    f"Skipping {src.name}: could not determine "
                    f"destination from tree view"
                )
                self._error_log.add_skipped(
                    str(src), "DFF",
                    "Could not determine destination from tree view",
                )
                return None
            dest = output_root / rel.with_suffix(".dsf")
        else:
            dest = src.parent / "converted" / (src.stem + ".dsf")

        return ConversionTask(
            source=src, destination=dest, converter="dff2dsf",
        )

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _build_relative_map(
        self,
        node: FileNode,
        current_path: Path,
        result: Dict[Path, Path],
    ) -> None:
        """
        Recursively traverse the tree and map each file's absolute
        path to its relative path from the tree root.
        """
        for i in range(node.child_count()):
            child = node.child(i)
            child_rel = current_path / child.name

            if child.node_type in (
                child.FILE, child.ISO,
            ) if hasattr(child, 'FILE') else False:
                pass

            from app.models.file_node import NodeType

            if child.node_type in (NodeType.FILE, NodeType.ISO):
                if child.path is not None:
                    result[child.path] = child_rel
            else:
                self._build_relative_map(child, child_rel, result)

    @staticmethod
    def _extract_disc_number(filename: str) -> Optional[int]:
        """
        Extract a disc number from an ISO filename.

        Looks for patterns like ``SACD8``, ``Disc 9``, ``D1``, ``CD10``,
        or a trailing number like ``album1``.
        """
        match = re.search(
            r"(?:sacd|disc|disco|disk|cd|d)\s*(\d+)",
            filename, re.IGNORECASE,
        )
        if match:
            return int(match.group(1))
        # Fallback: any trailing number.
        match = re.search(r"(\d+)\s*$", filename)
        if match:
            return int(match.group(1))
        return None



