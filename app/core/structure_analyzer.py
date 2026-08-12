"""
Folder-structure analyser for HiResToolsGUI.

Infers artist, album, disc, and track metadata from file-system paths
without reading any audio metadata.  Used by the scanner to build a
correct tree view and by the tag editor to pre-fill missing ID3 tags.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


#: Patterns that identify a disc sub-folder (case-insensitive).
_DISC_PATTERNS = re.compile(
    r"^(cd|disc|disco|disk)\s*\d+$|^disc\s+\w+$",
    re.IGNORECASE,
)


@dataclass
class TrackInfo:
    """Metadata for a single audio file inferred from its path."""
    path: Path
    track_number: int = 0
    track_title: str = ""


@dataclass
class AlbumInfo:
    """Metadata for an album inferred from folder structure."""
    artist: str = ""
    album: str = ""
    disc: str = ""
    tracks: List[TrackInfo] = field(default_factory=list)


class StructureAnalyzer:
    """
    Analyses a flat list of file paths and groups them into
    :class:`AlbumInfo` objects based on folder hierarchy.

    The expected layout is::

        ... / Artist / Album [/ Disc] / file.ext

    Where *Disc* is optional and matched by :attr:`_DISC_PATTERNS`.
    """

    #: Regex to extract a leading track number from a filename.
    _TRACK_NUM_RE = re.compile(r"^(\d+)\s*[-.]?\s*")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------


    @classmethod
    def analyse(cls, files: List[Path]) -> List[AlbumInfo]:
        """
        Group *files* by ``Artist/Album[/Disc]`` and infer metadata.

        Returns one :class:`AlbumInfo` per unique album folder.
        """
        albums: Dict[Path, AlbumInfo] = {}

        for file_path in files:
            album_dir, disc = cls._find_album_dir(file_path)
            if album_dir is None:
                continue

            if album_dir not in albums:
                parts = album_dir.parts
                artist = parts[-2] if len(parts) >= 2 else ""
                album = parts[-1] if len(parts) >= 1 else ""
                albums[album_dir] = AlbumInfo(
                    artist=cls._normalise_case(artist),
                    album=cls._normalise_case(album),
                    disc=disc,
                )

            track = cls._infer_track(file_path)
            albums[album_dir].tracks.append(track)

        # Sort tracks by track number within each album.
        for info in albums.values():
            info.tracks.sort(key=lambda t: t.track_number)

        return list(albums.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _find_album_dir(cls, file_path: Path) -> Tuple[Optional[Path], str]:
        """
        Walk up from *file_path* to locate the album directory.

        Returns ``(album_dir, disc)`` where *disc* is the disc sub-folder
        name (empty string if none).
        """
        parts = list(file_path.parts)
        if len(parts) < 3:
            return None, ""

        # File is in parts[-1], parent is parts[-2].
        parent = parts[-2]
        if cls._is_disc_folder(parent):
            # Structure: .../Artist/Album/Disc/file.ext
            if len(parts) < 4:
                return None, ""
            album_dir = Path(*parts[:-2])
            disc = parent
        else:
            # Structure: .../Artist/Album/file.ext
            album_dir = Path(*parts[:-1])
            disc = ""

        return album_dir, disc


    @classmethod
    def _is_disc_folder(cls, name: str) -> bool:
        """Return ``True`` if *name* looks like a disc sub-folder."""
        return bool(_DISC_PATTERNS.match(name))


    @classmethod
    def _infer_track(cls, file_path: Path) -> TrackInfo:
        """Extract track number and title from a file name."""
        stem = file_path.stem
        match = cls._TRACK_NUM_RE.match(stem)
        if match:
            number = int(match.group(1))
            title = stem[match.end():].strip()
        else:
            number = 0
            title = stem

        return TrackInfo(
            path=file_path,
            track_number=number,
            track_title=cls._normalise_case(title),
        )


    @staticmethod
    def _normalise_case(text: str) -> str:
        """
        Convert UPPERCASE text to Title Case.

        Preserves text that is already mixed-case.
        """
        if not text:
            return text
        if text.isupper():
            return text.title()
        return text


