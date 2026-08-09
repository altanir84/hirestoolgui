"""
Path-sanitisation utilities used before launching ``dff2dsf``.

Files whose paths contain characters that would require complex shell
escaping (e.g. newlines, unpaired quotes) are flagged as problematic
and skipped during conversion.
"""

from __future__ import annotations

import string
from pathlib import Path
from typing import List, Tuple


class PathValidator:
    """
    Validate file-system paths for safe consumption by ``QProcess``.

    ``QProcess`` passes arguments directly to the OS (no shell
    interpolation), so the main concern is characters that may confuse
    the receiving tool or the terminal if output is logged.

    Attributes
    ----------
    SAFE_CHARS:
        Set of characters guaranteed to be harmless in absolute paths
        on Linux.
    """

    # Printable ASCII minus characters that are common trouble-makers
    # in command-line tools (backslash, backtick, dollar, etc.).
    
    LATIN_EXTRA = (
        "ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØ"
        "ÙÚÛÜÝÞß"
        "àáâãäåæçèéêëìíîïðñòóôõöø"
        "ùúûüýþÿ"
        "ĀāĂăĄąĆćĈĉĊċČčĎďĐđĒēĔĕĖėĘęĚě"
        "ĜĝĞğĠġĢģĤĥĦħĨĩĪīĬĭĮįİıĲĳĴĵĶķĹĺĻļĽľĿŀŁł"
        "ŃńŅņŇňŊŋŌōŎŏŐőŒœŔŕŖŗŘřŚśŜŝŞşŠšŢţŤťŦŧ"
        "ŨũŪūŬŭŮůŰűŲųŴŵŶŷŸŹźŻżŽž"
    )

    SAFE_CHARS = set(
        string.ascii_letters +
        string.digits +
        LATIN_EXTRA +
        " /._-+:=(),@'![]#$%&~"
    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def validate(cls, path: Path) -> Tuple[bool, str]:
        """
        Check whether *path* is safe for use as a command-line argument.

        Returns
        -------
        (is_safe, reason)
            *is_safe* is ``True`` when the path contains only characters
            from :attr:`SAFE_CHARS`.  *reason* is an empty string on
            success or a human-readable explanation on failure.
        """
        raw = str(path)
        for idx, char in enumerate(raw):
            if char not in cls.SAFE_CHARS:
                return (
                    False,
                    (
                        f"Unsafe character U+{ord(char):04X} "
                        f"('{char}') at position {idx} in: {raw}"
                    ),
                )
        return True, ""

    @classmethod
    def filter_batch(
        cls,
        files: List[Path],
    ) -> Tuple[List[Path], List[Tuple[Path, str]]]:
        """
        Split *files* into safe and rejected lists.

        Returns
        -------
        (valid, rejected)
            *valid* contains paths that pass validation.
            *rejected* contains ``(path, reason)`` tuples for each
            problematic file.
        """
        valid: List[Path] = []
        rejected: List[Tuple[Path, str]] = []

        for file_path in files:
            ok, reason = cls.validate(file_path)
            if ok:
                valid.append(file_path)
            else:
                rejected.append((file_path, reason))

        return valid, rejected


