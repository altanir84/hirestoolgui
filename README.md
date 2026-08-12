# HiResToolsGUI

A graphical interface for converting high-resolution audio files on Linux.

**DFF to DSF** via `dff2dsf` and **SACD ISO to audio files** via `sacd_extract`.

Built with PySide6 and Python 3.10+.

---

## Features

**File management**
- **Recursive folder scanning** for `.dff`, `.DFF`, `.iso` and `.ISO` files
- **Hierarchical tree view** with tri-state checkboxes for file selection
- **Multiple folder selection** — add several root folders at once via a checkable directory tree
- **Drag-and-drop** folder support
- **Remove Selected** via checkboxes — remove root folders by checking them and clicking Remove Selected

**Conversion**
- **Dual converter support:**
  - `dff2dsf` — DFF → DSF conversion
  - `sacd_extract` — SACD ISO → DSF/DSDIFF/ISO extraction with stereo, multi-channel, CUE sheet, and output format options
- **CUE sheet auto-enable** — CUE sheet is forced on and locked when DSDIFF Edit Master is selected, as it is required for that format
- **Two output modes:**
  - **Single root** — replicates `Artist/Album[/Disc]` folder structure under one directory
  - **Per folder** — creates a `converted/` subfolder next to each source file
- **Automatic ISO sector conversion** — detects and converts 2064-byte sector SACD-R images to 2048-byte on the fly

- **Path validation** with exportable rejection list
- **Pre-conversion summary dialog** showing file counts by type and destination folders
- **Destination collision handling** — skip or overwrite existing files
- **Per-track progress bar** during SACD extraction showing real-time track completion
- **Cancellable** batch conversion

**Tags and naming**
- **ID3 tag preservation** — copies all existing tags from DFF to DSF; only missing fields are added when inferred
- **Tag editor** — for DFF files missing minimum metadata, infers artist/album/track from folder structure with a review dialog before conversion
- **Intelligent case normalisation** — when the majority of tracks in an album are UPPERCASE, normalises filenames, ID3 tags (DSF and DFF), and CUE sheet contents to Title Case, preserving intentional mixed-case words and acronyms

**Interface**
- **Persistent configuration** via QSettings — binary paths, output mode, last visited folder, SACD options
- **Detailed log output** with success/failure summary, full log file path, and separate error log for non-processed files
- **Dark mode** support via system theme detection

---

## Requirements

- **Python** 3.10 or later
- **[dff2dsf](https://signalyst.com/)** — DFF to DSF command-line converter (Signalyst) — Linux version
- **[sacd_extract](https://github.com/setmind/sacd-ripper)** — SACD ISO extraction tool for Linux

### Python packages

PySide6
mutagen

Install with:


pip install -r requirements.txt

---

## Installation
```bash
git clone https://github.com/altanir84/hirestoolgui.git
cd hirestoolgui
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Usage

python3 main.py

1. Configure the paths to dff2dsf and sacd_extract in the Converter Configuration panel. The application auto-detects them if they are on your $PATH.

2. Add one or more root folders using Add Folder, Add Multiple, or drag-and-drop.

3. Select files to convert using the checkboxes in the tree view. Use Select All / Deselect All for bulk selection. Remove root folders by checking them and clicking Remove    Selected.

4. Choose the output mode and destination in the Output Mode panel.

5. For ISO files, configure SACD extraction options in the SACD Extraction Options panel (stereo/multi-channel, CUE sheet, output format).

6. Click Start Conversion. Review the summary dialog, handle any path warnings or destination collisions, and confirm. If DFF files are missing metadata, a tag editor will open for review.


---

## Project Structure

```text
hirestoolgui/
├── main.py                         # Application entry point
├── requirements.txt                # Python dependencies
└── app/
    ├── __init__.py
    ├── main_window.py              # Main window — UI assembly and signal wiring
    ├── core/
    │   ├── __init__.py
    │   ├── conversion_orchestrator.py  # Batch lifecycle: threads, workers, progress polling
    │   ├── converter_worker.py         # Sequential converter (dff2dsf + sacd_extract) in a QThread
    │   ├── file_scanner.py             # Recursive filesystem scanner for .dff and .iso files
    │   ├── path_validator.py           # Path safety validation for command-line arguments
    │   ├── post_processor.py           # Post-conversion normalisation (filenames, ID3 tags, CUE sheets)
    │   ├── structure_analyzer.py       # Folder-structure analyser for artist/album/disc inference
    │   ├── tag_assurance.py            # Pre-conversion tag verification and editor integration
    │   ├── tag_preserver.py            # ID3 tag cache and restore (DFF → DSF via Mutagen)
    │   └── task_builder.py             # ConversionTask construction from file paths
    ├── models/
    │   ├── __init__.py
    │   ├── file_node.py                # Tree data structures (NodeType, CheckState, FileNode)
    │   └── file_tree_model.py          # QStandardItemModel backing the tree view
    ├── utils/
    │   ├── __init__.py
    │   └── logger.py                   # In-memory ring buffer, file-based logging, error log
    └── widgets/
        ├── __init__.py
        ├── config_panel.py             # Binary path selection (dff2dsf + sacd_extract) with validation
        ├── dialogs.py                  # Reusable dialogs (path warnings, collisions, confirmation)
        ├── file_panel.py               # File tree view with toolbar and status bar
        ├── output_panel.py             # Output mode selection (single root / per folder)
        ├── progress_panel.py           # Progress bars + cancellable log view
        ├── sacd_panel.py               # SACD extraction options (channels, CUE, output format)
        └── tag_editor_dialog.py        # Modal dialog for reviewing and editing inferred tags
```
---

## Configuration

Settings are persisted via QSettings:

Linux: ~/.config/HiResToolsGUI/HiResToolsGUI.conf

Logs: ~/.HiResToolsGUI/logs/

---

## License

This project is licensed under the MIT License. See LICENSE for details.

---

## Acknowledgements

This application was developed with the assistance of AI (DeepSeek V4 Pro) for code generation, architecture design, and debugging.



