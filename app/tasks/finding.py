# app/tasks/finding.py
import logging
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.config import AppConfig
from app.core.utils import find_files_by_extensions
from app.services.asset_handlers import ASSET_HANDLERS


def _parse_wrapper(file_path: Path):
    """
    Helper function to run asset parsing safely.
    Catches exceptions to ensure one bad file doesn't crash the whole thread pool.
    """
    try:
        handler = ASSET_HANDLERS.get(file_path.suffix.lower())
        if handler:
            return handler.parse(file_path)
    except Exception as e:
        logging.warning(f"Error parsing {file_path.name}: {e}")
    return set()


class UnusedAssetFinder:
    """
    Task to find 'Orphaned' assets - files that exist on disk
    but are not referenced by any material, level, or script.
    """

    def __init__(self, root: Path, signals):
        self.root = root
        self.signals = signals

    def run(self) -> dict:
        logging.info("Indexing filesystem for unused assets...")
        assets = set()
        containers = []

        # Extensions we consider "Assets" (Textures, Models)
        asset_exts = AppConfig.TEXTURE_EXTENSIONS.union({".cgf", ".cga", ".chr", ".skin"})

        # Map: normalized_stem -> relative_path
        asset_map = {}

        # 1. Scan filesystem (Fast IO operation)
        for root, _, files in os.walk(self.root):
            for f in files:
                path = Path(root) / f
                suffix = path.suffix.lower()

                # Identify Assets
                if suffix in asset_exts:
                    try:
                        rel_path_obj = path.relative_to(self.root)
                        stem = rel_path_obj.with_suffix("").as_posix().lower()
                        assets.add(stem)
                        asset_map[stem] = rel_path_obj.as_posix()
                    except ValueError:
                        pass

                # Identify Containers (files that hold references)
                if suffix in ASSET_HANDLERS:
                    containers.append(path)

        # 2. Parse containers to find references (CPU/IO bound)
        refs = set()
        logging.info(f"Scanning {len(containers)} container files...")

        # Use ThreadPoolExecutor for stability on Windows (avoids multiprocessing pickling issues)
        max_workers = (os.cpu_count() or 1) * 2

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(_parse_wrapper, f): f for f in containers}

            for i, future in enumerate(as_completed(future_map), 1):
                # Update progress every 20 files to reduce signal overhead
                if i % 20 == 0 or i == len(containers):
                    self.signals.progressUpdated.emit(i, len(containers))

                try:
                    found_refs = future.result()
                    for r in found_refs:
                        # Store reference as a stem (no extension) for fuzzy matching
                        refs.add(Path(r).with_suffix("").as_posix().lower())
                except Exception:
                    # Errors are already logged in _parse_wrapper
                    pass

        # 3. Determine unused assets
        unused = [asset_map[s] for s in assets if s not in refs]

        summary = f"Found {len(unused)} unused assets."
        return {
            "summary": summary,
            "unused_files": sorted(unused),
            "total_assets": len(assets),
            "duration": 0,
        }


class MissingAssetFinder:
    """
    Task to find 'Broken References' - files referenced in materials/scripts
    that do not exist on the disk.
    """

    def __init__(self, root: Path, signals):
        self.root = root
        self.signals = signals

    def run(self) -> dict:
        logging.info("Scanning for broken references...")

        # Find all files that can contain references
        containers = find_files_by_extensions(self.root, tuple(ASSET_HANDLERS.keys()))

        missing_map = defaultdict(list)
        # Cache existence checks to reduce OS calls: { "path/to/file": bool }
        cache = {}

        max_workers = (os.cpu_count() or 1) * 2

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(_parse_wrapper, f): f for f in containers}

            for i, future in enumerate(as_completed(future_map), 1):
                self.signals.progressUpdated.emit(i, len(containers))

                container_path = future_map[future]
                try:
                    container_rel = container_path.relative_to(self.root).as_posix()
                except ValueError:
                    container_rel = container_path.name

                try:
                    referenced_paths = future.result()
                    for ref in referenced_paths:
                        if ref not in cache:
                            # Check exact path
                            exists = (self.root / ref).exists()

                            # Check fuzzy (e.g., .tif referenced but .dds exists)
                            if not exists and Path(ref).suffix.lower() in {".tif", ".png", ".tga"}:
                                dds_path = self.root / Path(ref).with_suffix(".dds")
                                exists = dds_path.exists()

                            cache[ref] = exists

                        if not cache[ref]:
                            missing_map[ref].append(container_rel)
                except Exception:
                    pass

        summary = f"Found {len(missing_map)} broken references."
        return {
            "summary": summary,
            "missing_map": dict(missing_map),
            "duration": 0,
            "total_scanned": len(containers),
        }
