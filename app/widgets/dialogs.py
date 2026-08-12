"""
Reusable dialogs for HiResToolsGUI.

Provides static methods for path-validation warnings, destination
collision handling, and pre-conversion confirmation.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QWidget,
)

from app.core.converter_worker import ConversionTask


class Dialogs:
    """Collection of static dialog helpers."""

    # ------------------------------------------------------------------
    # Path validation warning
    # ------------------------------------------------------------------

    @staticmethod
    def warn_rejected_files(
        parent: QWidget,
        rejected: List[Tuple[Path, str]],
        valid_count: int,
    ) -> bool:
        """
        Show a dialog listing path-rejected files.

        Loops until the user chooses Continue or Cancel.  Export List
        saves the list and re-opens the dialog.

        Returns ``True`` when the user chose to continue.
        """
        if not rejected:
            return True

        while True:
            lines = []
            for rp, reason in rejected:
                lines.append(f"• {rp.name}")
                lines.append(f"  {reason}")
            detail = "\n".join(lines)

            msg = (
                f"{len(rejected)} file(s) have unsafe characters in "
                f"their paths and will be skipped.\n\n"
                f"{detail}\n\n"
                f"{valid_count} file(s) remain valid for conversion."
            )

            dlg = QMessageBox(parent)
            dlg.setWindowTitle("Path Validation Warning")
            dlg.setText(msg)
            dlg.setIcon(QMessageBox.Warning)

            btn_continue = dlg.addButton(
                "Continue Anyway", QMessageBox.AcceptRole
            )
            btn_export = dlg.addButton(
                "Export List...", QMessageBox.ActionRole
            )
            btn_cancel = dlg.addButton("Cancel", QMessageBox.RejectRole)

            dlg.exec()
            clicked = dlg.clickedButton()

            if clicked is btn_continue:
                return True

            if clicked is btn_cancel:
                return False

            if clicked is btn_export:
                path, _ = QFileDialog.getSaveFileName(
                    parent, "Save Rejected Files List",
                    str(Path.home() / "rejected_files.txt"),
                    "Text Files (*.txt)",
                )
                if path:
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write("Rejected files — HiResToolsGUI\n")
                        fh.write("=" * 60 + "\n\n")
                        for rp, reason in rejected:
                            fh.write(f"{rp}\n  {reason}\n\n")
                # Loop back to dialog.

    # ------------------------------------------------------------------
    # Destination collision
    # ------------------------------------------------------------------

    @staticmethod
    def handle_destination_collisions(
        parent: QWidget,
        tasks: List[ConversionTask],
    ) -> Tuple[List[ConversionTask], bool]:
        """
        Scan *tasks* for pre-existing destination files.

        Returns ``(tasks, overwrite)`` where *overwrite* is ``True``
        when the user chose to overwrite all.
        """
        collisions = [t for t in tasks if t.destination.exists()]
        if not collisions:
            return tasks, False

        names = "\n".join(
            f"  • {t.destination.name}" for t in collisions[:15]
        )
        suffix = (
            f"\n  ... and {len(collisions) - 15} more"
            if len(collisions) > 15
            else ""
        )

        msg = (
            f"{len(collisions)} destination file(s) already exist:\n\n"
            f"{names},{suffix}\n\n"
            f"How should these be handled?"
        )

        dlg = QMessageBox(parent)
        dlg.setWindowTitle("Destination Files Already Exist")
        dlg.setText(msg)
        dlg.setIcon(QMessageBox.Warning)

        btn_skip = dlg.addButton(
            "Skip Existing", QMessageBox.AcceptRole
        )
        btn_overwrite = dlg.addButton(
            "Overwrite All", QMessageBox.DestructiveRole
        )
        btn_cancel = dlg.addButton("Cancel", QMessageBox.RejectRole)

        dlg.exec()
        clicked = dlg.clickedButton()

        if clicked is btn_cancel:
            return [], False
        if clicked is btn_overwrite:
            return tasks, True
        return [t for t in tasks if not t.destination.exists()], False

    # ------------------------------------------------------------------
    # Pre-conversion confirmation
    # ------------------------------------------------------------------

    @staticmethod
    def confirm_conversion(
        parent: QWidget,
        tasks: List[ConversionTask],
    ) -> bool:
        """
        Show a summary dialog before conversion begins.

        Returns ``True`` when the user confirms.
        """
        folders = sorted({t.destination.parent for t in tasks})
        folder_list = "\n".join(f"  • {f}" for f in folders[:5])
        if len(folders) > 5:
            folder_list += f"\n  ... and {len(folders) - 5} more"

        iso_count = sum(
            1 for t in tasks if t.converter == "sacd_extract"
        )
        dff_count = sum(
            1 for t in tasks if t.converter == "dff2dsf"
        )

        msg = (
            f"Ready to convert {len(tasks)} file(s) to "
            f"{len(folders)} destination folder(s):\n\n"
            f"  DFF → dff2dsf: {dff_count}\n"
            f"  ISO → sacd_extract: {iso_count}\n\n"
            f"{folder_list}\n\n"
            f"Proceed?"
        )

        dlg = QMessageBox(parent)
        dlg.setWindowTitle("Confirm Conversion")
        dlg.setText(msg)
        dlg.setIcon(QMessageBox.Question)
        dlg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dlg.setDefaultButton(QMessageBox.Yes)

        return dlg.exec() == QMessageBox.Yes
