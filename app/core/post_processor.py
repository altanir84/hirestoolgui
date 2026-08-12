"""
Post-processing utilities for HiResToolsGUI.

Handles filename normalisation (UPPERCASE → Title Case), CUE-sheet
title correction, and ID3 tag normalisation for DSF and DFF files
after conversion.

Normalisation is applied only when the majority of tracks in an album
are entirely uppercase — this preserves intentional mixed-case or
acronym-based naming chosen by the artist.
"""

from __future__ import annotations

import re
from pathlib import Path
from mutagen.dsf import DSF
from mutagen.dsdiff import DSDIFF
from typing import List


class PostProcessor:
    """
    Stateless post-conversion normalisation.

    All methods are static; the class exists solely for namespace
    organisation.
    """

    #: CUE-sheet keywords whose quoted values should be normalised.
    _CUE_NORMALISE_KEYS = frozenset({"PERFORMER", "TITLE", "FILE"})

    #: Threshold ratio of uppercase tracks above which the whole album
    #: is considered to be in need of normalisation.
    _UPPERCASE_THRESHOLD = 0.5

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def process_sacd_output(cls, dest_dir: Path) -> None:
        """
        Normalise filenames, ID3 tags, and CUE-sheet contents in
        *dest_dir*.

        Normalisation is only applied when the majority of ``.dsf``
        and/or ``.dff`` stems in the directory are entirely uppercase.
        """
        if not cls._should_normalise(dest_dir):
            return

        # Normalise filenames.
        for f in dest_dir.iterdir():
            if f.is_file() and f.suffix.lower() in (
                ".dsf", ".dff", ".cue", ".xml",
            ):
                normalised = cls._normalise_filename(f)
                if normalised != f:
                    try:
                        f.rename(normalised)
                    except OSError:
                        pass

        # Normalise ID3 tags inside audio files.
        for f in dest_dir.iterdir():
            if f.is_file() and f.suffix.lower() in (".dsf", ".dff"):
                cls._normalise_audio_tags(f)

        # Normalise CUE sheet contents.
        cue_files = list(dest_dir.glob("*.cue"))
        for cue_file in cue_files:
            cls._normalise_cue_titles(cue_file)

    @classmethod
    def process_dff_output(cls, dest: Path) -> None:
        """
        Rename *dest* if its stem is all uppercase.
        """
        normalised = cls._normalise_filename(dest)
        if normalised != dest:
            try:
                dest.rename(normalised)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Majority detection
    # ------------------------------------------------------------------

    @classmethod
    def _should_normalise(cls, dest_dir: Path) -> bool:
        """
        Return ``True`` when the majority of ``.dsf`` and ``.dff``
        stems in *dest_dir* are entirely uppercase.
        """
        stems: List[str] = []
        for f in dest_dir.iterdir():
            if f.is_file() and f.suffix.lower() in (".dsf", ".dff"):
                stems.append(f.stem)

        if not stems:
            return False

        uppercase_count = sum(
            1 for s in stems if cls._needs_normalisation(s)
        )
        return uppercase_count / len(stems) > cls._UPPERCASE_THRESHOLD

    # ------------------------------------------------------------------
    # Case helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _needs_normalisation(text: str) -> bool:
        """
        Return ``True`` when *text* contains at least one letter and
        every letter is uppercase.
        """
        letters = [c for c in text if c.isalpha()]
        return len(letters) > 0 and all(c.isupper() for c in letters)

    @staticmethod
    def _normalise_text(text: str) -> str:
        """
        Normalise a string word-by-word: UPPERCASE words become Title
        Case; mixed-case words are preserved.
        """

        def _replace(match):
            word = match.group(0)
            if PostProcessor._needs_normalisation(word):
                return word.title()
            return word

        return re.sub(r"[A-Za-z]+", _replace, text)

    @classmethod
    def _normalise_filename(cls, path: Path) -> Path:
        """
        Convert a filename stem to Title Case word-by-word.

        Mixed-case words are preserved; only fully uppercase words
        are normalised.
        """
        stem = cls._normalise_text(path.stem)
        return path.with_name(stem + path.suffix)

    @classmethod
    def _normalise_audio_tags(cls, audio_path: Path) -> None:
        """
        Normalise UPPERCASE ID3 tag values in a DSF or DFF file
        word-by-word.
        """
        try:
            suffix = audio_path.suffix.lower()
            if suffix == ".dsf":
                audio = DSF(str(audio_path))
            elif suffix == ".dff":
                audio = DSDIFF(str(audio_path))
            else:
                return

            if audio.tags is None:
                return

            changed = False
            for frame in audio.tags.values():
                if hasattr(frame, "text") and isinstance(
                    frame.text, list
                ):
                    new_text = []
                    for item in frame.text:
                        text_str = str(item)
                        normalised = cls._normalise_text(text_str)
                        new_text.append(normalised)
                        if text_str != normalised:
                            changed = True
                    if changed:
                        frame.text = new_text

            if changed:
                audio.save()
        except Exception:
            pass

    @classmethod
    def _normalise_cue_titles(cls, cue_path: Path) -> None:
        """
        Normalise quoted values of PERFORMER, TITLE and FILE entries
        in a CUE sheet word-by-word.
        """
        try:
            text = cue_path.read_text(encoding="utf-8")
        except Exception:
            return

        lines = text.splitlines()
        changed = False
        new_lines = []

        for line in lines:
            stripped = line.strip()
            upper = stripped.upper()

            matched_key = None
            for key in cls._CUE_NORMALISE_KEYS:
                if upper.startswith(key + " "):
                    matched_key = key
                    break

            if matched_key is None:
                new_lines.append(line)
                continue

            start = stripped.find('"')
            end = stripped.rfind('"')
            if start == -1 or end == -1 or start >= end:
                new_lines.append(line)
                continue

            original_value = stripped[start + 1:end]
            normalised = cls._normalise_text(original_value)
            if normalised != original_value:
                line = line.replace(
                    f'"{original_value}"', f'"{normalised}"'
                )
                changed = True

            new_lines.append(line)

        if changed:
            try:
                cue_path.write_text(
                    "\n".join(new_lines), encoding="utf-8"
                )
            except Exception:
                pass
