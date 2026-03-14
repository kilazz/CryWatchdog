import logging
import os
import threading
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

from app.config import AppConfig
from app.core.utils import find_files_by_extensions, normalize_path
from app.services.asset_handlers import ASSET_HANDLERS


def _index_parse_worker(file_path: Path, root_path: Path) -> tuple[str | None, set[str] | None]:
    """
    Worker function for the index builder.
    """
    try:
        rel_path = normalize_path(file_path.relative_to(root_path))
    except ValueError:
        return None, None

    Handler = ASSET_HANDLERS.get(file_path.suffix.lower())
    if not Handler:
        return None, None

    for _ in range(10):
        try:
            if file_path.exists() and file_path.stat().st_size > 0:
                return rel_path, Handler.parse(file_path)
        except (OSError, ValueError):
            pass
        time.sleep(0.05)
    return rel_path, None


class AssetReferenceIndex:
    """
    In-memory bidirectional index of asset references.
    """

    def __init__(self, root_path: Path, signals, **kwargs: bool):
        self.root_path = root_path
        self.signals = signals
        self.dry_run = kwargs.get("dry_run", False)
        self.match_any_texture_extension = kwargs.get("match_any_texture_extension", True)
        self.allow_dir_change = kwargs.get("allow_dir_change", True)

        self._lock = threading.Lock()
        self._write_cooldowns = {}
        self.reference_to_containers = defaultdict(set)
        self.container_to_references = defaultdict(set)

    def is_on_cooldown(self, abs_path: Path) -> bool:
        return time.time() < self._write_cooldowns.get(abs_path, 0)

    def build_index(self):
        logging.info("Building asset reference index...")
        container_files = find_files_by_extensions(self.root_path, tuple(ASSET_HANDLERS.keys()))

        if not container_files:
            logging.warning("No container files found. Index is empty.")
            return

        with ProcessPoolExecutor(max_workers=os.cpu_count() or 1) as executor:
            worker_func = partial(_index_parse_worker, root_path=self.root_path)
            parsed_results = [r for r in executor.map(worker_func, container_files) if r and r[0] and r[1] is not None]

        with self._lock:
            self.reference_to_containers.clear()
            self.container_to_references.clear()
            for container_rel_path, found_refs in parsed_results:
                self.container_to_references[container_rel_path] = found_refs
                for ref in found_refs:
                    self.reference_to_containers[ref].add(container_rel_path)

        logging.info(f"Index built. Tracking references in {len(self.container_to_references)} files.")

    def process_container_file(self, container_abs_path: Path):
        if self.is_on_cooldown(container_abs_path):
            return

        result = _index_parse_worker(container_abs_path, self.root_path)
        if not result or not result[0]:
            return

        container_rel_path, found_refs = result
        if found_refs is None:
            return

        with self._lock:
            if container_rel_path in self.container_to_references:
                for old_ref in self.container_to_references[container_rel_path]:
                    if self.reference_to_containers.get(old_ref):
                        self.reference_to_containers[old_ref].discard(container_rel_path)
                        if not self.reference_to_containers[old_ref]:
                            del self.reference_to_containers[old_ref]

            self.container_to_references[container_rel_path] = found_refs
            for ref in found_refs:
                self.reference_to_containers[ref].add(container_rel_path)

    def remove_container_from_index(self, container_abs_path: Path):
        if self.is_on_cooldown(container_abs_path):
            return
        try:
            container_rel_path = normalize_path(container_abs_path.relative_to(self.root_path))
        except ValueError:
            return

        with self._lock:
            if container_rel_path in self.container_to_references:
                old_refs = self.container_to_references.pop(container_rel_path, set())
                for ref in old_refs:
                    if self.reference_to_containers.get(ref):
                        self.reference_to_containers[ref].discard(container_rel_path)

    def update_asset_path(self, old_abs_path: Path, new_abs_path: Path):
        try:
            old_rel_path = normalize_path(old_abs_path.relative_to(self.root_path))
            new_rel_path = normalize_path(new_abs_path.relative_to(self.root_path))
        except ValueError:
            return

        replacements = {}
        old_variants = set()
        new_variants = set()

        is_texture = old_abs_path.suffix.lower() in AppConfig.TEXTURE_EXTENSIONS
        if self.match_any_texture_extension and is_texture:
            old_stem = normalize_path(Path(old_rel_path).with_suffix(""))
            new_stem = normalize_path(Path(new_rel_path).with_suffix(""))
            for ext in AppConfig.TEXTURE_EXTENSIONS:
                old_v = f"{old_stem}{ext}"
                new_v = f"{new_stem}{ext}"
                old_variants.add(old_v.lower())
                new_variants.add(new_v.lower())
                replacements[old_v] = new_v
        else:
            old_variants.add(old_rel_path.lower())
            new_variants.add(new_rel_path.lower())
            replacements[old_rel_path] = new_rel_path

        if old_abs_path.suffix.lower() == ".mtl":
            old_no_ext = normalize_path(Path(old_rel_path).with_suffix(""))
            new_no_ext = normalize_path(Path(new_rel_path).with_suffix(""))
            old_variants.add(old_no_ext.lower())
            new_variants.add(new_no_ext.lower())
            replacements[old_no_ext] = new_no_ext

        with self._lock:
            affected_containers = set()
            for v in old_variants:
                if v in self.reference_to_containers:
                    affected_containers.update(self.reference_to_containers[v])

            if not affected_containers:
                return

            logging.info(
                f"Rename detected: '{old_rel_path}' -> '{new_rel_path}'. Patching {len(affected_containers)} file(s)..."
            )

            for rel_path_str in affected_containers:
                Handler = ASSET_HANDLERS.get(Path(rel_path_str).suffix.lower())
                if Handler:
                    full_path = self.root_path / rel_path_str
                    if self.dry_run:
                        logging.info(f"  [DRY RUN] Would patch: {rel_path_str}")
                    else:
                        Handler.rewrite(full_path, replacements, is_dir_move=False)
                        self._write_cooldowns[full_path] = time.time() + 2.0

            # Update In-Memory Index
            for old_v in old_variants:
                if old_v in self.reference_to_containers:
                    containers_to_move = self.reference_to_containers.pop(old_v)
                    for new_v in new_variants:
                        self.reference_to_containers[new_v].update(containers_to_move)

            for container in affected_containers:
                if container in self.container_to_references:
                    self.container_to_references[container] -= old_variants
                    self.container_to_references[container].update(new_variants)

    def handle_directory_move(self, old_dir_abs: Path, new_dir_abs: Path):
        if not self.allow_dir_change:
            return
        try:
            old_dir_rel = normalize_path(old_dir_abs.relative_to(self.root_path))
            new_dir_rel = normalize_path(new_dir_abs.relative_to(self.root_path))
        except ValueError:
            return

        with self._lock:
            prefix = old_dir_rel.lower() + "/"
            affected_containers = {
                c for c, refs in self.container_to_references.items() if any(r.lower().startswith(prefix) for r in refs)
            }

            if not affected_containers:
                return

            logging.info(
                f"Directory rename: '{old_dir_rel}' -> '{new_dir_rel}'. Patching {len(affected_containers)} files..."
            )

            replacements = {old_dir_rel: new_dir_rel}
            for rel_path_str in affected_containers:
                Handler = ASSET_HANDLERS.get(Path(rel_path_str).suffix.lower())
                if Handler:
                    full_path = self.root_path / rel_path_str
                    if self.dry_run:
                        logging.info(f"  [DRY RUN] Would patch (Dir Move): {rel_path_str}")
                    else:
                        Handler.rewrite(full_path, replacements, is_dir_move=True)
                        self._write_cooldowns[full_path] = time.time() + 2.0

        self.signals.indexingStarted.emit()
        self.build_index()
        self.signals.indexingFinished.emit()
