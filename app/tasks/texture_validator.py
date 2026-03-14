# app/tasks/texture_validator.py
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import ClassVar


class TextureValidator:
    """
    Task to validate texture assets.
    1. Identifies source textures (.tif, .png, etc.).
    2. Checks if the compiled .dds version exists.
    3. Checks if the source is newer than the compiled file (outdated).
    """

    # Source formats commonly used in CryEngine/Lumberyard/O3DE
    # RUF012: Mutable class attributes should be annotated with ClassVar
    SOURCE_EXTS: ClassVar[set[str]] = {".tif", ".tiff", ".png", ".tga", ".bmp", ".gif"}

    def __init__(self, project_root: Path, signals):
        self.project_root = project_root
        self.signals = signals

    def _check_pair(self, source_path: Path) -> tuple[str, str] | None:
        """
        Worker function to check a single source-compiled pair.
        Returns: (status_code, relative_path) or None.
        """
        try:
            # In CryEngine pipeline, the compiled file is usually .dds
            # located in the same folder as the source.
            dds_path = source_path.with_suffix(".dds")

            # Calculate relative path for reporting
            try:
                rel_path = source_path.relative_to(self.project_root).as_posix()
            except ValueError:
                rel_path = source_path.name

            # Check 1: Does compiled file exist?
            if not dds_path.exists():
                return ("missing", rel_path)

            # Check 2: Is source newer than compiled?
            src_mtime = source_path.stat().st_mtime
            dds_mtime = dds_path.stat().st_mtime

            # We add a 2.0 second buffer to account for file system time precision differences
            # and copy delays.
            if src_mtime > dds_mtime + 2.0:
                return ("outdated", rel_path)

        except OSError:
            # Handle permission errors or locked files gracefully
            pass

        return None

    def run(self) -> dict:
        logging.info("Starting Texture Validation scan...")
        start_time = time.time()

        # 1. Collect all source files (Fast I/O)
        source_files = []
        for root, _, files in os.walk(self.project_root):
            for f in files:
                path = Path(root) / f
                if path.suffix.lower() in self.SOURCE_EXTS:
                    source_files.append(path)

        if not source_files:
            return {"summary": "No source textures found in project."}

        outdated = []
        missing = []

        # 2. Process pairs in parallel (to speed up 'stat' calls on Windows)
        max_workers = min(32, (os.cpu_count() or 1) * 4)
        logging.info(f"Checking {len(source_files)} textures with {max_workers} threads...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(self._check_pair, f): f for f in source_files}

            for i, future in enumerate(as_completed(future_map), 1):
                # Update progress periodically
                if i % 50 == 0 or i == len(source_files):
                    self.signals.progressUpdated.emit(i, len(source_files))

                try:
                    result = future.result()
                    if result:
                        status, path = result
                        if status == "missing":
                            missing.append(path)
                        elif status == "outdated":
                            outdated.append(path)
                except Exception as e:
                    logging.warning(f"Error checking texture: {e}")

        duration = time.time() - start_time
        summary = (
            f"Scan Complete in {duration:.2f}s.\n"
            f"Outdated Textures (Source newer than DDS): {len(outdated)}\n"
            f"Missing Compiled Files (No DDS found): {len(missing)}"
        )

        logging.info(f"✅ {summary}")

        return {
            "summary": summary,
            "outdated": sorted(outdated),
            "missing": sorted(missing),
            "duration": duration,
        }
