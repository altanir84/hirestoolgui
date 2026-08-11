"""
ID3 tag preservation for DFF → DSF conversion.

Reads metadata from a source DFF file via :mod:`mutagen` and writes it
to the destination DSF file after conversion by ``dff2dsf``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from mutagen.dsdiff import DSDIFF
from mutagen.dsf import DSF
from mutagen.id3 import TIT2, TPE1, TALB, TRCK, ID3


class TagPreserver:
    """
    Caches ID3 tags from DFF sources and applies them to DSF outputs.

    Usage
    -----
    >>> preserver = TagPreserver()
    >>> preserver.cache_tags("/path/to/source.dff")
    >>> # ... run dff2dsf ...
    >>> preserver.apply_tags("/path/to/source.dff", "/path/to/output.dsf")
    """

    def __init__(self) -> None:
        self._cache: Dict[Path, ID3] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def cache_tags(self, source: Path) -> bool:
        """
        Read ID3 tags from *source* (DFF) and store them in memory.

        Returns ``True`` when tags were found and cached, ``False``
        when the file has no tags or cannot be read.
        """
        try:
            audio = DSDIFF(str(source))
            if audio.tags is None:
                return False
            # Deep-copy frames to avoid mutation issues.
            self._cache[source] = ID3()
            for frame in audio.tags.values():
                self._cache[source].add(frame)
            return True
        except Exception:
            return False


    @staticmethod
    def _complete_tags(
        tags,
        artist: str,
        album: str,
        track_number: int,
        track_title: str,
    ) -> None:
        """
        Ensure *tags* has the minimum required frames, adding only
        what is missing.  Existing frames are preserved.
        """
        
        if "TIT2" not in tags:
            tags.add(TIT2(encoding=3, text=track_title))
        if "TPE1" not in tags:
            tags.add(TPE1(encoding=3, text=artist))
        if "TALB" not in tags:
            tags.add(TALB(encoding=3, text=album))
        if "TRCK" not in tags:
            tags.add(TRCK(encoding=3, text=str(track_number)))


    def apply_tags(self, source: Path, destination: Path) -> bool:
        """
        Write cached tags from *source* into *destination* (DSF).

        Returns ``True`` on success, ``False`` when no cached tags
        exist for *source* or the destination cannot be written.
        """
        tags = self._cache.pop(source, None)
        if tags is None:
            return False

        try:
            audio = DSF(str(destination))
            if audio.tags is None:
                audio.add_tags()
            audio.tags.clear()
            for frame in tags.values():
                audio.tags.add(frame)
            audio.save()
            return True
        except Exception:
            return False


    def has_tags(self, source: Path) -> bool:
        """Return ``True`` if tags are already cached for *source*."""
        return source in self._cache    


    def clear(self) -> None:
        """Discard all cached tags."""
        self._cache.clear()


