"""
Sequential converter that invokes ``dff2dsf`` or ``sacd_extract`` via
:class:`subprocess.Popen` inside a single :class:`QThread`.

Reads stdout line-by-line to emit per-track progress for SACD extraction.
"""

from __future__ import annotations

import re
import signal
import subprocess
from pathlib import Path
import queue
from typing import List, NamedTuple, Optional, Tuple

from PySide6.QtCore import QObject, Signal, Slot


class ConversionTask(NamedTuple):
    """Description of a single file to convert."""
    source: Path
    destination: Path
    converter: str  # "dff2dsf" or "sacd_extract"


class ConverterWorker(QObject):
    """
    Runs conversions sequentially inside a dedicated thread.

    Parameters
    ----------
    binary_dff2dsf:
        Absolute path to the ``dff2dsf`` executable.
    binary_sacd_extract:
        Absolute path to the ``sacd_extract`` executable.
    tasks:
        Ordered list of :class:`ConversionTask` items.
    sacd_stereo:
        ``True`` to extract stereo channels (``-2``).
    sacd_multichannel:
        ``True`` to extract multi-channel (``-m``).
    sacd_cue:
        ``True`` to export CUE sheet (``-C``).
    sacd_output_format:
        CLI flag for output format (``-s``, ``-p``, ``-e``, ``-I``).
    cancel_event:
        A :class:`threading.Event` for graceful cancellation.
    overwrite:
        ``True`` to overwrite existing destination files.

    Signals
    -------
    task_started(source, dest):
        Emitted immediately before launching the converter.
    task_finished(source, dest, exit_code, error_output):
        Emitted after the process completes.
    task_skipped(source, reason):
        Emitted when a task is skipped (e.g. collision rename).
    task_progress(current, total, message):
        Emitted during SACD extraction for each track processed.
    all_done():
        Emitted after the last task has been processed or cancelled.
    """

    task_started = Signal(str, str)
    task_finished = Signal(str, str, int, str)
    task_skipped = Signal(str, str)
    task_progress = Signal(int, int, str)
    all_done = Signal()

    # Regex for SACD track progress lines:
    #   Processing: filename.dsf (3/16)..
    _TRACK_RE = re.compile(r"Processing\s.*\((\d+)/(\d+)\)")

    def __init__(
        self,
        binary_dff2dsf: str,
        binary_sacd_extract: str,
        tasks: List[ConversionTask],
        sacd_stereo: bool = True,
        sacd_multichannel: bool = False,
        sacd_cue: bool = False,
        sacd_output_format: str = "-s",
        cancel_event=None,
        overwrite: bool = False,
    ) -> None:
        super().__init__()
        self._binary_dff2dsf = binary_dff2dsf
        self._binary_sacd_extract = binary_sacd_extract
        self._tasks = tasks
        self._sacd_stereo = sacd_stereo
        self._sacd_multichannel = sacd_multichannel
        self._sacd_cue = sacd_cue
        self._sacd_output_format = sacd_output_format
        self._cancel = cancel_event
        self._overwrite = overwrite

        self._progress_queue = queue.Queue()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    @Slot()
    def run(self) -> None:
        """Process every task sequentially and emit ``all_done``."""
        for task in self._tasks:
            if self._cancel is not None and self._cancel.is_set():
                break

            source_str = str(task.source)
            dest = task.destination

            dest.parent.mkdir(parents=True, exist_ok=True)

            final_dest = dest
            skip_reason = ""
            if final_dest.exists():
                if self._overwrite:
                    final_dest.unlink()
                else:
                    final_dest = self._find_available_name(final_dest)
                    skip_reason = (
                        f"Renamed to avoid collision: {final_dest.name}"
                    )
                    self.task_skipped.emit(source_str, skip_reason)

            dest_str = str(final_dest)
            self.task_started.emit(source_str, dest_str)

            if task.converter == "sacd_extract":
                exit_code, stderr = self._run_sacd_extract(
                    source_str, str(final_dest.parent)
                )
            else:
                exit_code, stderr = self._run_dff2dsf(source_str, dest_str)

            self.task_finished.emit(source_str, dest_str, exit_code, stderr)

        self.all_done.emit()

    # ------------------------------------------------------------------
    # Converter-specific runners
    # ------------------------------------------------------------------

    def _run_dff2dsf(self, source: str, dest: str):
        """Invoke ``dff2dsf source dest`` and return (exit_code, stderr)."""
        return self._run_process(
            [self._binary_dff2dsf, source, dest]
        )

    def _run_sacd_extract(self, source: str, output_dir: str):
        """
        Invoke ``sacd_extract`` with the configured flags.

        Reads stdout line-by-line to emit ``task_progress`` for each
        track processed.
        """
        args = [self._binary_sacd_extract, self._sacd_output_format, "-c", "-i", source]

        if self._sacd_stereo:
            args.append("-2")
        if self._sacd_multichannel:
            args.append("-m")
        if self._sacd_cue:
            args.append("-C")

        args.extend(["-y", output_dir])

        return self._run_process_with_progress(args)

    def _run_process(self, args: List[str]):
        """Execute *args* via :class:`subprocess.run` and return (exit_code, stderr)."""
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                timeout=600,
                text=True,
            )
            return proc.returncode, proc.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "TIMEOUT"
        except Exception as exc:
            return -2, str(exc)

    def _run_process_with_progress(self, args: List[str]):
        """
        Execute *args* via a pseudo-terminal so that ``sacd_extract``
        produces line-buffered output, then parse track progress.

        Detects fatal SACD errors (e.g. invalid ScarletBook disc) and
        forces exit code 0 when tracks were successfully extracted
        despite PTY-related noise.
        """
        import os
        import pty

        try:
            master_fd, slave_fd = pty.openpty()
            proc = subprocess.Popen(
                args,
                stdout=slave_fd,
                stderr=slave_fd,
                text=True,
                close_fds=True,
            )
            os.close(slave_fd)

            stdout = os.fdopen(master_fd, "r", buffering=1)
            error_detected = False
            tracks_extracted = False

            for line in stdout:
                line = line.strip()
                if not line:
                    continue

                match = self._TRACK_RE.search(line)
                if match:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    self._progress_queue.put((current, total, line))
                    tracks_extracted = True

                if (
                    "Not a ScarletBook disc" in line
                    or "Errors reading sacd data" in line
                ):
                    error_detected = True

                if "program terminates" in line.lower():
                    break

            try:
                
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    proc.wait(timeout=3)
                except Exception:
                    
                    proc.kill()
                    proc.wait()


            if error_detected:
                return -1, "Not a valid SACD ISO (ScarletBook disc required)"

            if tracks_extracted:
                return 0, ""

            return proc.returncode, ""

        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.wait()
            except Exception:
                pass
            return -1, "TIMEOUT"
        except Exception as exc:
            return -2, str(exc)


    def get_progress(self) -> Optional[Tuple[int, int, str]]:
        """Non-blocking read from the progress queue"""
        try:
            return self._progress_queue.get_nowait()
        except queue.Empty:
            return None



    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_available_name(original: Path) -> Path:
        """Generate a non-colliding filename by appending ``_1``, ``_2``, …"""
        stem = original.stem
        suffix = original.suffix
        parent = original.parent
        counter = 1
        while True:
            candidate = parent / f"{stem}_{counter},{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1


