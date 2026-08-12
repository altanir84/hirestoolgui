"""
Conversion task builder for HiResToolsGUI.

Constructs :class:`ConversionTask` objects from a flat list of file
paths, handling both DFF and ISO sources with correct destination
path resolution.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from app.core.converter_worker import ConversionTask
from app.utils.logger import ErrorLogManager, LogManager
from app.widgets.output_panel import OutputPanel


class TaskBuilder:
    """
    Builds :class:`ConversionTask` objects for DFF and ISO files.

    DFF files use ``dff2dsf``; ISO files use ``sacd_extract``.
    For ISO files in single-root mode, the output directory points
    to the *Artist* folder because ``sacd_extract -y`` creates the
    album sub-folder automatically.
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
    ) -> List[ConversionTask]:
        """
        Convert a flat list of checked file paths into tasks.

        Files that do not meet the ``Artist/Album`` folder-structure
        requirement are skipped with a warning.
        """
        tasks: List[ConversionTask] = []

        for src in files:
            if src.suffix.lower() == ".iso":
                task = self._build_iso_task(src, mode, output_root)
            else:
                task = self._build_dff_task(src, mode, output_root)
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
    ) -> Optional[ConversionTask]:
        """Build a task for an ISO file, or ``None`` if skipped."""
        if mode == OutputPanel.MODE_SINGLE:
            dest_dir = self._iso_dest_dir(src, output_root)
            if dest_dir is None:
                self._log_manager.warning(
                    f"Skipping {src.name}: file must reside "
                    f"inside an Artist/Album folder hierarchy"
                )
                self._error_log.add_skipped(
                    str(src), "ISO",
                    "File not inside Artist/Album folder hierarchy",
                )
                return None
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
    ) -> Optional[ConversionTask]:
        """Build a task for a DFF file, or ``None`` if skipped."""
        if mode == OutputPanel.MODE_SINGLE:
            rel = self._artist_album_relative(src)
            if rel is None:
                self._log_manager.warning(
                    f"Skipping {src.name}: file must reside "
                    f"inside an Artist/Album folder hierarchy"
                )
                self._error_log.add_skipped(
                    str(src), "DFF",
                    "File not inside Artist/Album folder hierarchy",
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

    @staticmethod
    def _artist_album_relative(file_path: Path) -> Optional[Path]:
        """
        Derive the relative ``Artist/Album[/Disc]/filename`` path from
        an absolute *file_path*.

        Returns ``None`` when fewer than two parent directories exist
        above the file.
        """
        parts = file_path.parts
        if len(parts) < 4:
            return None
        levels = list(parts[-4:-1])
        filename = parts[-1]
        return Path(*levels) / filename


    @staticmethod
    def _iso_dest_dir(
        file_path: Path, output_root: Path,
    ) -> Optional[Path]:
        """
        Compute the destination directory for an ISO extraction.

        Returns ``output_root/Artist/Album[/Disc]`` so that
        ``sacd_extract -y <dir>`` writes tracks into the correct
        location without creating an extra nested folder.
        """
        parts = file_path.parts
        if len(parts) < 4:
            return None
        levels = list(parts[-4:-1])
        return output_root / Path(*levels)
