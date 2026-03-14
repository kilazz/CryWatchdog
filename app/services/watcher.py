# app/services/watcher.py
import difflib
import logging
import threading
import time
from pathlib import Path
from typing import TypedDict

from watchfiles import Change, watch

from app.config import AppConfig
from app.services.asset_handlers import ASSET_HANDLERS
from app.services.index import AssetReferenceIndex


class WatcherOptions(TypedDict, total=False):
    dry_run: bool
    match_any_texture_extension: bool
    allow_dir_change: bool


class WatcherSettings(TypedDict):
    project_root: Path
    watcher_options: WatcherOptions


class WatcherService:
    def __init__(self, settings: WatcherSettings, signals):
        self.settings = settings
        self.signals = signals
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        if self.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def is_alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def _run(self):
        try:
            self.signals.indexingStarted.emit()
            options = self.settings.get("watcher_options", {})
            index = AssetReferenceIndex(self.settings["project_root"], self.signals, **options)
            index.build_index()

            if self.stop_event.is_set():
                return
            self.signals.indexingFinished.emit()

            mode_str = "[DRY RUN ENABLED]" if options.get("dry_run") else "[LIVE MODE]"
            logging.info(f"Watchfiles started on: {self.settings['project_root']} {mode_str}")

            container_exts = tuple(ASSET_HANDLERS.keys())
            tracked_exts = AppConfig.TRACKED_ASSET_EXTENSIONS
            _last_deleted = []  # list of (path, time)

            for changes in watch(str(self.settings["project_root"]), stop_event=self.stop_event):
                added_paths = []
                deleted_paths = []
                modified_paths = []

                for change, path_str in changes:
                    path = Path(path_str)
                    if change == Change.added:
                        added_paths.append(path)
                    elif change == Change.deleted:
                        deleted_paths.append(path)
                    elif change == Change.modified:
                        modified_paths.append(path)

                current_time = time.time()
                # Clean up old deleted paths (> 1.0s)
                _last_deleted = [(p, t) for p, t in _last_deleted if current_time - t < 1.0]

                # Add new deleted paths to the tracking list
                for p in deleted_paths:
                    _last_deleted.append((p, current_time))

                # Detect Renames
                renames = []
                for added in added_paths[:]:
                    matching_deleted = None

                    # 1. Try to find a deleted file with the exact same name (Move to different folder)
                    exact_name_matches = [p for p, t in _last_deleted if p.name == added.name]
                    if len(exact_name_matches) == 1 or len(exact_name_matches) > 1:
                        matching_deleted = exact_name_matches[0]
                    else:
                        # 2. Try to find a deleted file in the same directory (Rename in same folder)
                        candidates = [p for p, t in _last_deleted if p.parent == added.parent]

                        if len(candidates) == 1:
                            matching_deleted = candidates[0]
                        elif len(candidates) > 1:
                            # Multiple candidates, find the most similar filename
                            best_match = None
                            best_ratio = 0.0
                            for c in candidates:
                                ratio = difflib.SequenceMatcher(None, c.name, added.name).ratio()
                                if ratio > best_ratio:
                                    best_ratio = ratio
                                    best_match = c
                            matching_deleted = best_match
                        elif len(_last_deleted) == 1 and len(added_paths) == 1:
                            # 3. Exactly 1 deleted and 1 added recently, assume rename/move
                            matching_deleted = _last_deleted[0][0]

                    if matching_deleted:
                        renames.append((matching_deleted, added))
                        # Remove from tracking
                        _last_deleted = [(p, t) for p, t in _last_deleted if p != matching_deleted]
                        added_paths.remove(added)
                        if matching_deleted in deleted_paths:
                            deleted_paths.remove(matching_deleted)

                for old_path, new_path in renames:
                    logging.info(f"Detected rename: {old_path.name} -> {new_path.name}")
                    if old_path.is_dir() or new_path.is_dir() or not old_path.suffix:
                        # It might be a directory rename
                        index.handle_directory_move(old_path, new_path)
                    elif old_path.suffix.lower() in tracked_exts:
                        index.update_asset_path(old_path, new_path)

                for path in added_paths:
                    if path.suffix.lower() in container_exts and not index.is_on_cooldown(path):
                        index.process_container_file(path)

                for path in modified_paths:
                    if path.suffix.lower() in container_exts and not index.is_on_cooldown(path):
                        index.process_container_file(path)

                for path in deleted_paths:
                    if path.suffix.lower() in container_exts and not index.is_on_cooldown(path):
                        index.remove_container_from_index(path)

        except Exception as e:
            logging.error(f"Critical watcher error: {e}", exc_info=True)
            self.signals.criticalError.emit("Watcher Error", f"{e}")
        finally:
            logging.info("Watcher thread terminated.")
            self.signals.watcherStopped.emit()
