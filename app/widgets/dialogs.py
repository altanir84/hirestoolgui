"""
Reusable dialogs for HiResToolsGUI.

Provides static methods for path-validation warnings, destination
collision handling, pre-conversion confirmation, and the Help/About
dialogs.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QApplication
)

from app.core.converter_worker import ConversionTask
from app.utils.resources import resource_path


class Dialogs:
    """Collection of static dialog helpers."""

    _VERSION = "1.1.0"
    _AUTHOR = "Altanir Flores de Mello Junior"
    _YEAR = "2026"
    _GITHUB_URL = "https://github.com/altanir84/hirestoolsgui"

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

        Loops until the user chooses Continue or Cancel. Export List
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
            f" • {t.destination.name}" for t in collisions[:15]
        )
        suffix = (
            f"\n ... and {len(collisions) - 15} more"
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
        folder_list = "\n".join(f" • {f}" for f in folders[:5])
        if len(folders) > 5:
            folder_list += f"\n ... and {len(folders) - 5} more"

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

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    @classmethod
    def show_help(cls, parent: QWidget) -> None:
        """Open the Help dialog with tabbed usage instructions."""
        dialog = QDialog(parent)
        dialog.setWindowTitle("HiResToolsGUI — Help")
        dialog.resize(680, 520)
        dialog.setMinimumSize(500, 400)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.addTab(
            cls._help_tab(cls._help_overview()), "Overview"
        )
        tabs.addTab(
            cls._help_tab(cls._help_getting_started()),
            "Getting Started",
        )
        tabs.addTab(
            cls._help_tab(cls._help_output_structure()),
            "Output Structure",
        )
        tabs.addTab(
            cls._help_tab(cls._help_tags_naming()),
            "Tags & Naming",
        )
        tabs.addTab(
            cls._help_tab(cls._help_features()), "Features"
        )
        layout.addWidget(tabs)

        # Footer.
        footer = QHBoxLayout()
        footer.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        footer.addWidget(btn_close)

        layout.addLayout(footer)
        dialog.exec()

    # ------------------------------------------------------------------
    # About
    # ------------------------------------------------------------------

    @classmethod
    def show_about(cls, parent: QWidget) -> None:
        """Open the About dialog with logo, version, and GitHub link."""
        dialog = QDialog(parent)
        dialog.setWindowTitle("About HiResToolsGUI")
        dialog.setFixedSize(400, 360)
        dialog.setWindowFlags(
            dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )

        layout = QVBoxLayout(dialog)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 16)

        # Logo.
        logo_label = QLabel()
        logo_path = resource_path("assets/hirestoolsgui.svg")
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                logo_label.setPixmap(pixmap)
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)

        # Title.
        title_label = QLabel("HiResToolsGUI")
        title_font = title_label.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Info.
        info_label = QLabel(
            f"Version {cls._VERSION}\n\n"
            f"© {cls._YEAR} {cls._AUTHOR}\n\n"
            "A graphical tool for converting\n"
            "hi-res audio files (DFF → DSF)\n"
            "and extracting SACD ISO images."
        )
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addStretch()

        # Footer: GitHub icon + Close.
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)

        btn_github = QPushButton()
        btn_github.setFlat(True)
        btn_github.setCursor(Qt.PointingHandCursor)
        btn_github.setToolTip(cls._GITHUB_URL)
        btn_github.setFixedSize(28, 28)

        # Choose GitHub icon based on system theme.
        try:
            is_dark = (
                QApplication.styleHints().colorScheme()
                == Qt.ColorScheme.Dark
            )
        except AttributeError:
            is_dark = False

        github_filename = (
            "assets/github_white.svg"
            if is_dark
            else "assets/github.svg"
        )
        github_icon_path = resource_path(github_filename)

        if github_icon_path.exists():
            icon_pixmap = QPixmap(str(github_icon_path))
            if not icon_pixmap.isNull():
                btn_github.setIcon(icon_pixmap)
                btn_github.setIconSize(btn_github.size())
        btn_github.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(cls._GITHUB_URL))
        )
        footer.addWidget(btn_github)

        footer.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        footer.addWidget(btn_close)

        layout.addLayout(footer)
        dialog.exec()

    # ------------------------------------------------------------------
    # Help tab helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _help_tab(content: str) -> QWidget:
        """Wrap HTML *content* in a read-only ``QTextEdit``."""
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(content)
        text_edit.setStyleSheet(
            "QTextEdit { background-color: transparent; border: none; }"
        )
        return text_edit

    # ------------------------------------------------------------------
    # Help content — individual tabs
    # ------------------------------------------------------------------

    @classmethod
    def _help_overview(cls) -> str:
        return f"""
        <h2>HiResToolsGUI v{cls._VERSION}</h2>
        <p>HiResToolsGUI is a graphical application for converting
        hi-res audio files with an intuitive tree-based interface.</p>

        <h3>Supported Operations</h3>
        <ul>
            <li><b>DFF &rarr; DSF</b> conversion using
            <code>dff2dsf</code></li>
            <li><b>SACD ISO extraction</b> using
            <code>sacd_extract</code> — stereo, multichannel, CUE
            sheet export, and multiple output formats (DSF, DSDIFF,
            DSDIFF Edit Master, ISO)</li>
        </ul>

        <h3>Key Features</h3>
        <ul>
            <li>Recursive folder scanning with tri-state checkboxes</li>
            <li>Drag-and-drop folder support</li>
            <li>ID3 tag preservation (DFF &rarr; DSF)</li>
            <li>Intelligent case normalisation</li>
            <li>Automatic ISO sector conversion (2064 &rarr; 2048)</li>
            <li>Dark mode support</li>
        </ul>
        """

    @classmethod
    def _help_getting_started(cls) -> str:
        return """
        <style>
            ol li { margin-bottom : 8px; }
            ul li { margin-bottom : 4px; }
        </style>
        <h3>Step-by-Step Guide</h3>
        <ol>
            <li><b>Configure binaries:</b> Use the top panel to set
            the paths to <code>dff2dsf</code> and
            <code>sacd_extract</code>. A green check indicates a
            valid, executable binary.</li>
            <li><b>Add folders:</b> Click <i>Add Folder…</i> to
            import a single directory, or <i>Add Multiple…</i> to
            select several folders at once using a checkable
            directory tree.</li>
            <li><b>Select files:</b> Use the checkboxes in the tree
            view to choose which <code>.dff</code> and
            <code>.iso</code> files to convert. Use <i>Select
            All</i> / <i>Deselect All</i> for bulk operations.</li>
            <li><b>Choose output mode:</b>
                <ul>
                    <li><i>Single root</i> — replicates the tree-view
                    folder structure under one output directory.</li>
                    <li><i>Per folder</i> — creates a
                    <code>converted/</code> subfolder next to each
                    source file.</li>
                </ul>
            </li>
            <li><b>SACD options:</b> When ISO files are selected, the
            SACD panel becomes available. Choose stereo and/or
            multichannel extraction, CUE sheet generation, and output
            format.</li>
            <li><b>Start conversion:</b> Click <i>Start
            Conversion</i>, review the summary dialog, and confirm.
            Progress is shown in real time with per-track updates for
            SACD extraction.</li>
        </ol>
        """

    @classmethod
    def _help_output_structure(cls) -> str:
        return """
        <h3>How the Output Structure Is Determined</h3>
        <p>In <i>Single root</i> mode, the output folder hierarchy
        <b>mirrors exactly what is shown in the tree view</b>. The
        relative path of each checked file within the tree determines
        its destination under the chosen output root.</p>

        <p>For example, if your tree view shows:</p>
        <pre>  music/
          ├── DSD/
          │   └── Artist/
          │       └── Album/
          │           └── track.dff
          └── SACD/
              └── Artist/
                  └── Album/
                      └── image.iso</pre>
        <p>The output will preserve this entire structure under your
        chosen output directory.</p>

        <h3>Important Recommendation</h3>
        <p>For consistent and predictable results, add folders under
        a <b>single top-level root</b> (e.g.
        <code>/mnt/music</code>). Adding multiple unrelated roots
        (e.g. <code>/mnt/disk1/music</code> and
        <code>/mnt/disk2/music</code>) may produce conflicting
        structures in the output.</p>

        <h3>Multiple ISOs in the Same Folder</h3>
        <p>When several ISO files exist in the same source album
        folder, each is placed in its own <code>Disc1</code>,
        <code>Disc2</code>, … subfolder. The disc number is extracted
        from the filename when possible (e.g.
        <code>SACD2.iso</code> &rarr; <code>Disc2/</code>).</p>
        """

    @classmethod
    def _help_tags_naming(cls) -> str:
        return """
        <h3>ID3 Tag Preservation</h3>
        <p>All existing ID3 tags are copied from the source DFF file
        to the converted DSF file. Only missing fields are filled in
        when inferred from the folder structure.</p>

        <h3>Tag Editor</h3>
        <p>For DFF files missing minimum metadata (artist, album,
        track), a tag editor dialog appears before conversion,
        allowing you to review and edit the inferred values.</p>

        <h3>Intelligent Case Normalisation</h3>
        <p>When the majority of tracks in an album have fully
        UPPERCASE filenames and tags, the post-processor normalises
        them to Title Case. Mixed-case words and acronyms are
        preserved. This applies to:</p>
        <ul>
            <li>Filenames (<code>.dsf</code>, <code>.dff</code>,
            <code>.cue</code>)</li>
            <li>ID3 tags inside DSF and DFF files</li>
            <li>CUE sheet contents (PERFORMER, TITLE, FILE)</li>
        </ul>

        <h3>Multichannel Suffix</h3>
        <p>Files extracted in multichannel mode receive a
        <code>-mch</code> suffix (e.g. <code>track-mch.dsf</code>).
        CUE sheet references are updated accordingly.</p>
        """

    @classmethod
    def _help_features(cls) -> str:
        return """
        <h3>File Management</h3>
        <ul>
            <li><b>Refresh Tree:</b> re-scans only the folders
            currently shown in the tree view, skipping previously
            empty subdirectories.</li>
            <li><b>Rescan Folders:</b> re-scans all imported folders,
            including those that were previously empty. Useful when
            new files have been added.</li>
            <li><b>Reset Folders:</b> clears all imported folders and
            returns to the initial state.</li>
            <li><b>Remove Selected:</b> removes checked root folders
            from the tree view and refreshes.</li>
        </ul>

        <h3>Conversion</h3>
        <ul>
            <li><b>Cancel:</b> cancels scans and conversions in
            progress. Files already processed are kept.</li>
            <li><b>Per-track progress:</b> during SACD extraction, a
            track-level progress bar shows real-time completion.</li>
            <li><b>Path validation:</b> files with unsafe characters
            in their paths are flagged before conversion.</li>
            <li><b>Destination collision handling:</b> skip or
            overwrite existing files.</li>
        </ul>

        <h3>Interface</h3>
        <ul>
            <li>Persistent configuration via system settings (binary
            paths, output mode, last visited folder, SACD
            options).</li>
            <li>Dark mode support via system theme detection.</li>
            <li>Detailed log output with success/failure summary and
            separate error log for non-processed files.</li>
        </ul>
        """



