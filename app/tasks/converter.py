# app/tasks/converter.py
import contextlib
import logging
from pathlib import Path


class ProjectConverter:
    """A task class for converting all project filenames to lowercase."""

    def __init__(self, project_root: Path, signals):
        self.project_root = project_root
        self.signals = signals

    def run(self) -> dict:
        logging.info(f"Starting filename conversion in '{self.project_root}' to lowercase...")
        renamed_count = 0
        error_count = 0

        # Get all files and folders.
        # Note: We must convert paths to string for reliable sorting/processing in some OS edge cases,
        # but pathlib handles objects well.
        all_paths = list(self.project_root.rglob("*"))

        # Process in reverse order (deepest files first).
        # This prevents errors where renaming a parent folder makes child paths invalid
        # before we get to them.
        for i, path in enumerate(reversed(all_paths), 1):
            self.signals.progressUpdated.emit(i, len(all_paths))

            if path.name == path.name.lower():
                continue

            new_path = path.with_name(path.name.lower())

            # Case-insensitive FS collision check (Windows behavior)
            # If new_path exists AND it is NOT the same file (i.e. different inode or physical file),
            # then it's a real collision with another existing file.
            if new_path.exists() and not path.samefile(new_path):
                logging.error(f"  - [FAIL] Conflict: '{new_path.name}' already exists. Skipping.")
                error_count += 1
                continue

            try:
                # On Windows, renaming a file to its lowercase equivalent directly might fail or do nothing.
                # Rename to a temporary name first.
                temp_path = path.with_name(path.name + ".tmp_rename")
                path.rename(temp_path)
                temp_path.rename(new_path)
                renamed_count += 1
            except OSError as e:
                logging.error(f"  - [FAIL] Could not rename {path.name}: {e}")
                # Try to recover if the second rename failed
                if 'temp_path' in locals() and temp_path.exists():
                    with contextlib.suppress(OSError):
                        temp_path.rename(path)
                error_count += 1

        summary = f"Conversion complete. Renamed {renamed_count} items with {error_count} errors."
        logging.info(f"✅ {summary}")
        return {"summary": summary}
