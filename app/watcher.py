# app/watcher.py
import logging
import os
import threading
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

# This uses OS-level events (Windows API / Inotify) for zero-CPU idle usage.
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.asset_handlers import ASSET_HANDLERS
from app.config import AppConfig
from app.utils import CoreSignals, find_files_by_extensions


def _index_parse_worker(file_path: Path, root_path: Path) -> tuple[str | None, set[str] | None]:
    """
    Worker function for the index builder.
    Returns: (relative_path, set_of_refs) OR (relative_path, None) if read failed.
    """
    try:
        rel_path = file_path.relative_to(root_path).as_posix()
    except ValueError:
        return None, None

    Handler = ASSET_HANDLERS.get(file_path.suffix.lower())
    if not Handler:
        return None, None

    # Retry logic for locked files
    for _ in range(10):
        try:
            if file_path.exists() and file_path.stat().st_size > 0:
                return rel_path, Handler.parse(file_path)
        except (OSError, ValueError):
            pass
        time.sleep(0.05)

    # If still unreadable, return None to signal "keep old data"
    logging.warning(f"File busy/empty after retries: {rel_path}. Skipping update.")
    return rel_path, None


class AssetReferenceIndex:
    """
    In-memory bidirectional index of asset references.
    """

    def __init__(self, root_path: Path, signals: CoreSignals, **kwargs: bool):
        self.root_path = root_path
        self.signals = signals

        self.allow_extension_change = kwargs.get("allow_ext_change", True)
        self.allow_directory_change = kwargs.get("allow_dir_change", True)
        self.match_any_texture_extension = kwargs.get("match_any_texture_extension", True)

        self._lock = threading.Lock()
        self._write_cooldowns = {}

        self.reference_to_containers: dict[str, set[str]] = defaultdict(set)
        self.container_to_references: dict[str, set[str]] = defaultdict(set)

    def _to_rel_path(self, abs_path: Path) -> str | None:
        try:
            return abs_path.relative_to(self.root_path).as_posix()
        except ValueError:
            return None

    def is_on_cooldown(self, abs_path: Path) -> bool:
        """Check if we should ignore events for this path due to self-triggered writes."""
        return time.time() < self._write_cooldowns.get(abs_path, 0)

    def build_index(self):
        logging.info("Building asset reference index...")
        start_time = time.time()
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

        logging.info(
            f"Index built in {time.time() - start_time:.2f}s. "
            f"Tracking {len(self.reference_to_containers)} assets across {len(self.container_to_references)} files."
        )

    def process_container_file(self, container_abs_path: Path):
        """Updates the index for a single modified or created container file."""
        if self.is_on_cooldown(container_abs_path):
            return

        result = _index_parse_worker(container_abs_path, self.root_path)
        if not result:
            return

        container_rel_path, found_refs = result
        if not container_rel_path:
            return

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
        # Check cooldown here too! Don't delete index if we are just rewriting the file.
        if self.is_on_cooldown(container_abs_path):
            return

        container_rel_path = self._to_rel_path(container_abs_path)
        if not container_rel_path:
            return

        with self._lock:
            if container_rel_path in self.container_to_references:
                old_refs = self.container_to_references.pop(container_rel_path, set())
                for ref in old_refs:
                    if self.reference_to_containers.get(ref):
                        self.reference_to_containers[ref].discard(container_rel_path)
                        if not self.reference_to_containers.get(ref):
                            del self.reference_to_containers[ref]

    def update_asset_path(self, old_abs_path: Path, new_abs_path: Path):
        old_rel_path, new_rel_path = self._to_rel_path(old_abs_path), self._to_rel_path(new_abs_path)
        if not (old_rel_path and new_rel_path):
            return

        replacements = {}
        old_variants = set()
        new_variants = set()

        is_texture = old_abs_path.suffix.lower() in AppConfig.TEXTURE_EXTENSIONS

        if self.match_any_texture_extension and is_texture:
            old_stem = Path(old_rel_path).with_suffix("").as_posix()
            new_stem = Path(new_rel_path).with_suffix("").as_posix()
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
            old_no_ext = Path(old_rel_path).with_suffix("").as_posix()
            new_no_ext = Path(new_rel_path).with_suffix("").as_posix()
            old_variants.add(old_no_ext.lower())
            new_variants.add(new_no_ext.lower())
            replacements[old_no_ext] = new_no_ext

        with self._lock:
            affected_containers = set()
            for v in old_variants:
                if v in self.reference_to_containers:
                    affected_containers.update(self.reference_to_containers[v])

            if not affected_containers:
                logging.debug(f"Watchdog: No references found for {old_rel_path}")
                return

            logging.info(
                f"Rename detected: '{old_rel_path}' -> '{new_rel_path}'. Patching {len(affected_containers)} file(s)..."
            )

            for rel_path_str in affected_containers:
                Handler = ASSET_HANDLERS.get(Path(rel_path_str).suffix.lower())
                if Handler:
                    full_path = self.root_path / rel_path_str
                    Handler.rewrite(full_path, replacements, is_dir_move=False)

                    # Set Cooldown (2 seconds)
                    self._write_cooldowns[full_path] = time.time() + 2.0

            # Update In-Memory Index (TRUSTED)
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
        if not self.allow_directory_change:
            return

        old_dir_rel, new_dir_rel = self._to_rel_path(old_dir_abs), self._to_rel_path(new_dir_abs)
        if not (old_dir_rel and new_dir_rel):
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
                    Handler.rewrite(full_path, replacements, is_dir_move=True)
                    self._write_cooldowns[full_path] = time.time() + 2.0

        self.signals.indexingStarted.emit()
        self.build_index()
        self.signals.indexingFinished.emit()


class WatcherService:
    def __init__(self, settings: dict, signals: CoreSignals):
        self.settings = settings
        self.signals = signals
        self.observer: Observer | None = None
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self):
        if self.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        if self.is_alive():
            self.stop_event.set()
        if self.observer:
            self.observer.stop()
            self.observer.join()

    def is_alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def _run(self):
        self.observer = Observer()
        try:
            self.signals.indexingStarted.emit()
            index = AssetReferenceIndex(
                self.settings["project_root"], self.signals, **self.settings.get("watcher_options", {})
            )
            index.build_index()
            if self.stop_event.is_set():
                return
            self.signals.indexingFinished.emit()

            event_handler = ChangeHandler(index)
            self.observer.schedule(event_handler, str(self.settings["project_root"]), recursive=True)

            logging.info(f"Watchdog started on: {self.settings['project_root']}")
            self.observer.start()
            while not self.stop_event.is_set():
                time.sleep(0.5)
        except Exception as e:
            logging.error(f"Critical watcher error: {e}", exc_info=True)
            self.signals.criticalError.emit("Watcher Error", f"A critical error occurred: {e}")
        finally:
            if self.observer and self.observer.is_alive():
                self.observer.stop()
                if self.observer.is_alive():
                    self.observer.join()
            logging.info("Watcher thread terminated.")
            self.signals.watcherStopped.emit()


class ChangeHandler(FileSystemEventHandler):
    def __init__(self, index: AssetReferenceIndex):
        super().__init__()
        self.index = index
        self.container_exts = tuple(ASSET_HANDLERS.keys())
        self.tracked_exts = AppConfig.TRACKED_ASSET_EXTENSIONS
        self._last_deleted = {}

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        filename = path.name

        # Simulated Move Detection
        if filename in self._last_deleted:
            old_path, del_time = self._last_deleted[filename]
            if time.time() - del_time < 1.0:
                logging.info(f"Detected move via recreation: {old_path.name}")
                if path.suffix.lower() in self.tracked_exts:
                    self.index.update_asset_path(old_path, path)
                del self._last_deleted[filename]

        if path.suffix.lower() in self.container_exts and not self.index.is_on_cooldown(path):
            self.index.process_container_file(path)

    def on_modified(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in self.container_exts and not self.index.is_on_cooldown(path):
            self.index.process_container_file(path)

    def on_deleted(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)

        # Cache deletion for Move Detection
        if path.suffix.lower() in self.tracked_exts or path.suffix.lower() in self.container_exts:
            self._last_deleted[path.name] = (path, time.time())

        if path.suffix.lower() in self.container_exts and not self.index.is_on_cooldown(path):
            self.index.remove_container_from_index(path)

    def on_moved(self, event):
        src_path, dest_path = Path(event.src_path), Path(event.dest_path)
        if event.is_directory:
            self.index.handle_directory_move(src_path, dest_path)
        else:
            if src_path.suffix.lower() in self.tracked_exts:
                self.index.update_asset_path(src_path, dest_path)

            if src_path.suffix.lower() in self.container_exts and not self.index.is_on_cooldown(dest_path):
                self.index.remove_container_from_index(src_path)
                self.index.process_container_file(dest_path)
