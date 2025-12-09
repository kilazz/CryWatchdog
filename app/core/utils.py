# app/core/utils.py
import contextlib
import logging
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

from lxml import etree as ET


def ensure_writable(file_path: Path):
    """
    Attempts to make a file writable using Perforce (P4) or OS chmod.
    Critical for working in game dev environments (Perforce/Git) where files
    might be Read-Only.
    """
    if not file_path.exists():
        return

    # If already writable, skip
    if os.access(file_path, os.W_OK):
        return

    # 1. Try Perforce (P4) checkout
    try:
        # Check if 'p4' is available and file is tracked
        # Only run if inside a typical dev environment to avoid spamming subprocesses
        proc = subprocess.run(
            ["p4", "edit", str(file_path)],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if proc.returncode == 0:
            logging.info(f"Checked out file via P4: {file_path.name}")
            return
    except FileNotFoundError:
        pass  # P4 not installed or not in PATH

    # 2. Fallback: Force OS write attribute (Git/Local)
    try:
        os.chmod(file_path, stat.S_IWRITE)
        logging.info(f"Removed Read-Only attribute: {file_path.name}")
    except Exception as e:
        logging.warning(f"Failed to make {file_path.name} writable: {e}")


def atomic_write(file_path: Path, data: Any, **kwargs: Any):
    """
    Writes data to a temp file, ensures the target is writable, then replaces it.

    Includes Process ID (PID) in the temp filename to allow multiple instances
    of the tool to run safely on the same folder without collision.
    """
    # Create a unique temp file name: filename.ext.<PID>.tmp
    pid = os.getpid()
    temp_path = file_path.with_suffix(f"{file_path.suffix}.{pid}.tmp")

    try:
        # Prepare temp file
        if isinstance(data, str):
            # Extract arguments specifically for open()
            encoding = kwargs.get("encoding", "utf-8")
            newline = kwargs.get("newline")

            # Use open() context manager to strictly control line endings
            with open(temp_path, "w", encoding=encoding, newline=newline) as f:
                f.write(data)

        elif isinstance(data, bytes):
            temp_path.write_bytes(data)
        elif isinstance(data, ET._ElementTree):
            data.write(str(temp_path), **kwargs)
        else:
            raise TypeError(f"Unsupported data type: {type(data)}")

        # Ensure target is writable (P4/Git support)
        if file_path.exists():
            ensure_writable(file_path)

        # Atomic replace
        os.replace(temp_path, file_path)

    except Exception as e:
        logging.error(f"Atomic write to {file_path} failed: {e}")
        # Clean up temp file on failure
        if temp_path.exists():
            with contextlib.suppress(OSError):
                temp_path.unlink(missing_ok=True)
        raise


def find_files_by_extensions(root_path: Path, extensions: tuple[str, ...]) -> list[Path]:
    """
    Recursively finds all files in root_path matching the given extensions.
    """
    return [
        Path(root) / filename
        for root, _, files in os.walk(root_path)
        for filename in files
        if filename.lower().endswith(extensions)
    ]
