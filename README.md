# HiResToolsGUI

A graphical interface for converting high-resolution audio files in Linux OS.

**DFF to DSF** via `dff2dsf` and **SACD ISO to DSF** via `sacd_extract`.

Built with PySide6 and Python 3.10+. 

---

## Features

- **Recursive folder scanning** for `.dff`, `.DFF`, `.iso` and `.ISO` files
- **Hierarchical tree view** with tri-state checkboxes for file selection
- **Dual converter support:**
  - `dff2dsf` — DFF → DSF conversion with automatic ID3 tag preservation
  - `sacd_extract` — SACD ISO → DSF extraction with stereo, multi-channel, CUE sheet, and output format options
- **Two output modes:**
  - **Single root** — replicates `Artist/Album[/Disc]` folder structure under one directory
  - **Per folder** — creates a `converted/` subfolder next to each source file
- **Per-track progress bar** during SACD extraction showing real-time track completion
- **Persistent configuration** via QSettings — binary paths, output mode, last visited folder, SACD options
- **Drag-and-drop** folder support
- **Cancellable** batch conversion
- **Path validation** with exportable rejection list
- **Destination collision handling** — skip or overwrite existing files
- **Pre-conversion summary dialog** showing file counts by type and destination folders
- **Detailed log output** with success/failure summary and log file path
- **Dark mode** support via system theme detection

---

## Requirements

- **Python** 3.10 or later
- **[dff2dsf](https://signalyst.com/)** — DFF to DSF command-line converter (Signalyst) - Linux Version
- **[sacd_extract](https://github.com/setmind/sacd-ripper)** — SACD ISO extraction tool for Linux

### Python packages

PySide6
mutagen

Install with:


pip install -r requirements.txt

---

## Installation

git clone <repository-url>
cd dff2dsf_gui
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

---

## Usage

python main.py

1. Configure the paths to dff2dsf and sacd_extract in the Converter Configuration panel. The application auto-detects them if they are on your $PATH.

2. Add one or more root folders using Add Folder or drag-and-drop.

3. Select files to convert using the checkboxes in the tree view. Use Select All / Deselect All for bulk selection.

4. Choose the output mode and destination in the Output Mode panel.

5. For ISO files, configure SACD extraction options in the SACD Extraction Options panel (stereo/multi-channel, CUE sheet, output format).

6. Click Start Conversion. Review the summary dialog, handle any path warnings or destination collisions, and confirm.


---

## Project Structure

```text
hirestoolgui/
├── main.py                         # Application entry point
├── requirements.txt                # Python dependencies
└── app/
    ├── __init__.py
    ├── main_window.py              # Main window — orchestrates all panels and conversion lifecycle
    ├── core/
    │   ├── __init__.py
    │   ├── converter_worker.py     # Sequential converter (dff2dsf + sacd_extract) in a QThread
    │   ├── file_scanner.py         # Recursive filesystem scanner for .dff and .iso files
    │   ├── path_validator.py       # Path safety validation for command-line arguments
    │   └── tag_preserver.py        # ID3 tag cache and restore (DFF → DSF via Mutagen)
    ├── models/
    │   ├── __init__.py
    │   ├── file_node.py            # Tree data structures (NodeType, CheckState, FileNode)
    │   └── file_tree_model.py      # QStandardItemModel backing the tree view
    ├── utils/
    │   ├── __init__.py
    │   └── logger.py               # In-memory ring buffer + file-based logging
    └── widgets/
        ├── __init__.py
        ├── config_panel.py         # Binary path selection (dff2dsf + sacd_extract) with validation
        ├── file_panel.py           # File tree view with toolbar and status bar
        ├── output_panel.py         # Output mode selection (single root / per folder)
        ├── progress_panel.py       # Progress bars + cancellable log view
        └── sacd_panel.py           # SACD extraction options (channels, CUE, output format)
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



