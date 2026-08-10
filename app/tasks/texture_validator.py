from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from app.core.utils import get_safe_rel_path
from app.tasks.models import TextureValidatorResult

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class TextureValidator:
    SOURCE_EXTS: ClassVar[set[str]] = {".tif", ".tiff", ".png", ".tga", ".bmp", ".gif"}

    def __init__(self, project_root: Path, progress_callback: Callable[[int, int], None] | None = None):
        self.project_root = project_root
        self.progress_callback = progress_callback

    def _check_pair(self, source_path: Path) -> tuple[str, str] | None:
        try:
            dds_path = source_path.with_suffix(".dds")
            rel_path = get_safe_rel_path(source_path, self.project_root)

            if not dds_path.exists():
                return ("missing", rel_path)

            src_mtime = source_path.stat().st_mtime
            dds_mtime = dds_path.stat().st_mtime

            if src_mtime > dds_mtime + 2.0:
                return ("outdated", rel_path)

        except OSError:
            pass

        return None

    def run(self) -> TextureValidatorResult:
        logger.info("Starting Texture Validation scan...")
        start_time = time.time()

        source_files = []
        for root, _, files in os.walk(self.project_root):
            for f in files:
                path = Path(root) / f
                if path.suffix.lower() in self.SOURCE_EXTS:
                    source_files.append(path)

        if not source_files:
            return TextureValidatorResult(summary="No source textures found in project.")

        outdated = []
        missing = []

        max_workers = min(32, (os.cpu_count() or 1) * 4)
        logger.info(f"Checking {len(source_files)} textures with {max_workers} threads...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(self._check_pair, f): f for f in source_files}

            for i, future in enumerate(as_completed(future_map), 1):
                if (i % 50 == 0 or i == len(source_files)) and self.progress_callback:
                    self.progress_callback(i, len(source_files))

                try:
                    result = future.result()
                    if result:
                        status, path = result
                        if status == "missing":
                            missing.append(path)
                        elif status == "outdated":
                            outdated.append(path)
                except Exception as e:
                    logger.warning(f"Error checking texture: {e}")

        duration = time.time() - start_time
        summary = (
            f"Scan Complete in {duration:.2f}s.\n"
            f"Outdated Textures (Source newer than DDS): {len(outdated)}\n"
            f"Missing Compiled Files (No DDS found): {len(missing)}"
        )

        logger.info(f"✅ {summary}")

        return TextureValidatorResult(
            summary=summary,
            outdated=sorted(outdated),
            missing=sorted(missing),
            duration=duration,
        )
