from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class ProjectConverter:
    """A task class for converting all project filenames to lowercase."""

    def __init__(self, project_root: Path, signals):
        self.project_root = project_root
        self.signals = signals

    def run(self) -> dict:
        logger.info(f"Starting filename conversion in '{self.project_root}' to lowercase...")
        renamed_count = 0
        error_count = 0

        all_paths = list(self.project_root.rglob("*"))

        for i, path in enumerate(reversed(all_paths), 1):
            self.signals.progressUpdated.emit(i, len(all_paths))

            if path.name == path.name.lower():
                continue

            new_path = path.with_name(path.name.lower())

            if new_path.exists() and not path.samefile(new_path):
                logger.error(f"  - [FAIL] Conflict: '{new_path.name}' already exists. Skipping.")
                error_count += 1
                continue

            temp_path = None
            try:
                temp_path = path.with_name(path.name + ".tmp_rename")
                path.rename(temp_path)
                temp_path.rename(new_path)
                renamed_count += 1
            except OSError as e:
                logger.error(f"  - [FAIL] Could not rename {path.name}: {e}")
                if temp_path and temp_path.exists():
                    with contextlib.suppress(OSError):
                        temp_path.rename(path)
                error_count += 1

        summary = f"Conversion complete. Renamed {renamed_count} items with {error_count} errors."
        logger.info(f"✅ {summary}")
        return {"summary": summary}
