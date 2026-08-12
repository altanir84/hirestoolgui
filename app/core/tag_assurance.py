"""
Tag assurance for HiResToolsGUI.

Verifies that DFF files have minimum ID3 tags before conversion.
For albums where tags are missing, infers metadata from folder
structure and presents a dialog for user confirmation.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from mutagen.dsdiff import DSDIFF
from mutagen.id3 import ID3

from app.core.structure_analyzer import StructureAnalyzer
from app.core.tag_preserver import TagPreserver
from app.widgets.tag_editor_dialog import TagEditorDialog


class TagAssurance:
    """
    Ensures every DFF file has minimum ID3 tags before conversion.

    Existing tags are preserved; only missing fields are added from
    folder-structure inference with user confirmation.
    """

    def __init__(self, tag_preserver: TagPreserver) -> None:
        self._tag_preserver = tag_preserver

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_tags(self, dff_files: List[Path]) -> None:
        """
        Verify minimum ID3 tags for all *dff_files*.

        For albums where tags are missing, infer metadata from folder
        structure and present :class:`TagEditorDialog` for user
        confirmation.  Existing tags are never overwritten — only
        missing frames are added.
        """
        albums = StructureAnalyzer.analyse(dff_files)
        if not albums:
            return

        for album_info in albums:
            missing = False
            for track in album_info.tracks:
                try:
                    audio = DSDIFF(str(track.path))
                    tags = audio.tags
                    if tags is None:
                        missing = True
                        continue

                    required = {"TPE1", "TALB", "TIT2", "TRCK"}
                    existing = {frame.FrameID for frame in tags.values()}
                    if not required.issubset(existing):
                        missing = True

                    self._tag_preserver._cache[track.path] = tags

                    tpe1 = tags.get("TPE1")
                    talb = tags.get("TALB")
                    tit2 = tags.get("TIT2")
                    trck = tags.get("TRCK")

                    if tpe1 and not album_info.artist:
                        album_info.artist = str(tpe1)
                    if talb and not album_info.album:
                        album_info.album = str(talb)
                    if tit2:
                        track.track_title = str(tit2)
                    if trck:
                        try:
                            track.track_number = int(
                                str(trck).split("/")[0]
                            )
                        except ValueError:
                            pass
                except Exception:
                    missing = True

            if not missing:
                continue

            if not album_info.artist:
                album_info.artist = StructureAnalyzer._normalise_case(
                    album_info.artist or ""
                )
            if not album_info.album:
                album_info.album = StructureAnalyzer._normalise_case(
                    album_info.album or ""
                )

            dlg = TagEditorDialog(album_info)
            if dlg.exec() == TagEditorDialog.Accepted:
                updated = dlg.get_album_info()
                for track in updated.tracks:
                    tags = self._tag_preserver._cache.get(track.path)
                    if tags is None:
                        tags = ID3()
                    self._tag_preserver._complete_tags(
                        tags,
                        artist=updated.artist,
                        album=updated.album,
                        track_number=track.track_number,
                        track_title=track.track_title,
                    )
                    self._tag_preserver._cache[track.path] = tags
