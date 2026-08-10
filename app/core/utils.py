import contextlib
import logging
import os
import stat
import subprocess
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


def normalize_path(path: Path | str) -> str:
    path = path.as_posix() if isinstance(path, Path) else path.replace("\\", "/")
    return path


def get_safe_rel_path(file_path: Path, root_path: Path) -> str:
    try:
        return file_path.relative_to(root_path).as_posix()
    except ValueError:
        return file_path.name


def ensure_writable(file_path: Path):
    if not file_path.exists():
        return

    if os.access(file_path, os.W_OK):
        return

    try:
        proc = subprocess.run(
            ["p4", "edit", str(file_path)],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if proc.returncode == 0:
            logger.info(f"Checked out file via P4: {file_path.name}")
            return
    except FileNotFoundError:
        pass

    try:
        os.chmod(file_path, stat.S_IWRITE)
        logger.info(f"Removed Read-Only attribute: {file_path.name}")
    except Exception as e:
        logger.warning(f"Failed to make {file_path.name} writable: {e}")


def atomic_write(file_path: Path, data: Any, **kwargs: Any):
    pid = os.getpid()
    temp_path = file_path.with_suffix(f"{file_path.suffix}.{pid}.tmp")

    try:
        if isinstance(data, str):
            encoding = kwargs.get("encoding", "utf-8")
            newline = kwargs.get("newline")

            with open(temp_path, "w", encoding=encoding, newline=newline) as f:
                f.write(data)

        elif isinstance(data, bytes):
            temp_path.write_bytes(data)
        elif isinstance(data, ET.ElementTree):
            data.write(str(temp_path), **kwargs)
        else:
            raise TypeError(f"Unsupported data type: {type(data)}")

        if file_path.exists():
            ensure_writable(file_path)

        os.replace(temp_path, file_path)

    except Exception as e:
        logger.error(f"Atomic write to {file_path} failed: {e}")
        if temp_path.exists():
            with contextlib.suppress(OSError):
                temp_path.unlink(missing_ok=True)
        raise


def find_files_by_extensions(root_path: Path, extensions: tuple[str, ...]) -> list[Path]:
    return [
        Path(root) / filename
        for root, _, files in os.walk(root_path)
        for filename in files
        if filename.lower().endswith(extensions)
    ]
