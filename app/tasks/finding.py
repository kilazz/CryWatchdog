from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import AppConfig
from app.core.utils import find_files_by_extensions
from app.services.asset_handlers import ASSET_HANDLERS
from app.tasks.models import MissingAssetResult, UnusedAssetResult

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def _parse_wrapper(file_path: Path):
    try:
        handler = ASSET_HANDLERS.get(file_path.suffix.lower())
        if handler:
            return handler.parse(file_path)
    except Exception as e:
        logger.warning(f"Error parsing {file_path.name}: {e}")
    return set()


class UnusedAssetFinder:
    def __init__(self, root: Path, progress_callback: Callable[[int, int], None] | None = None):
        self.root = root
        self.progress_callback = progress_callback

    def run(self) -> UnusedAssetResult:
        start_time = time.time()
        logger.info("Indexing filesystem for unused assets...")
        assets = set()
        containers = []

        asset_exts = AppConfig.TEXTURE_EXTENSIONS.union({".cgf", ".cga", ".chr", ".skin"})
        asset_map = {}

        for root, _, files in os.walk(self.root):
            for f in files:
                path = Path(root) / f
                suffix = path.suffix.lower()

                if suffix in asset_exts:
                    try:
                        rel_path_obj = path.relative_to(self.root)
                        stem = rel_path_obj.with_suffix("").as_posix().lower()
                        assets.add(stem)
                        asset_map[stem] = rel_path_obj.as_posix()
                    except ValueError:
                        pass

                if suffix in ASSET_HANDLERS:
                    containers.append(path)

        refs = set()
        logger.info(f"Scanning {len(containers)} container files...")

        max_workers = (os.cpu_count() or 1) * 2

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(_parse_wrapper, f): f for f in containers}

            for i, future in enumerate(as_completed(future_map), 1):
                if (i % 20 == 0 or i == len(containers)) and self.progress_callback:
                    self.progress_callback(i, len(containers))

                try:
                    found_refs = future.result()
                    for r in found_refs:
                        refs.add(Path(r).with_suffix("").as_posix().lower())
                except Exception:
                    pass

        unused = [asset_map[s] for s in assets if s not in refs]

        summary = f"Found {len(unused)} unused assets."
        duration = time.time() - start_time

        return UnusedAssetResult(
            summary=summary,
            unused_files=sorted(unused),
            total_assets=len(assets),
            duration=duration,
        )


class MissingAssetFinder:
    def __init__(self, root: Path, progress_callback: Callable[[int, int], None] | None = None):
        self.root = root
        self.progress_callback = progress_callback

    def run(self) -> MissingAssetResult:
        start_time = time.time()
        logger.info("Scanning for broken references...")

        containers = find_files_by_extensions(self.root, tuple(ASSET_HANDLERS.keys()))

        missing_map = defaultdict(list)
        cache = {}

        max_workers = (os.cpu_count() or 1) * 2

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(_parse_wrapper, f): f for f in containers}

            for i, future in enumerate(as_completed(future_map), 1):
                if self.progress_callback:
                    self.progress_callback(i, len(containers))

                container_path = future_map[future]
                try:
                    container_rel = container_path.relative_to(self.root).as_posix()
                except ValueError:
                    container_rel = container_path.name

                try:
                    referenced_paths = future.result()
                    for ref in referenced_paths:
                        if ref not in cache:
                            exists = (self.root / ref).exists()

                            if not exists and Path(ref).suffix.lower() in {".tif", ".png", ".tga"}:
                                dds_path = self.root / Path(ref).with_suffix(".dds")
                                exists = dds_path.exists()

                            cache[ref] = exists

                        if not cache[ref]:
                            missing_map[ref].append(container_rel)
                except Exception:
                    pass

        summary = f"Found {len(missing_map)} broken references."
        duration = time.time() - start_time

        return MissingAssetResult(
            summary=summary,
            missing_map=dict(missing_map),
            total_scanned=len(containers),
            duration=duration,
        )
