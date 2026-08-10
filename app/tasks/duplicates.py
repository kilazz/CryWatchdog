from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class DuplicateFinder:
    def __init__(self, signals):
        self.signals = signals

    def _get_file_hash(self, filepath: Path) -> str | None:
        hasher = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.warning(f"Could not hash {filepath}: {e}")
            return None

    def run(self, folder_ref: Path, folder_target: Path) -> dict:
        logger.info(f"Starting Duplicate Scan.\n  Reference: {folder_ref}\n  Target: {folder_target}")

        if folder_ref == folder_target:
            return {"summary": "Error: Reference and Target folders cannot be the same."}

        duplicates = []
        bytes_saved = 0

        target_files = [p for p in folder_target.rglob("*") if p.is_file()]
        total_files = len(target_files)

        logger.info(f"Scanning {total_files} files in target against reference...")

        for i, path_b in enumerate(target_files, 1):
            if i % 10 == 0:
                self.signals.progressUpdated.emit(i, total_files)

            try:
                rel_path = path_b.relative_to(folder_target)
                path_a = folder_ref / rel_path

                if not path_a.exists():
                    continue

                size_b = path_b.stat().st_size
                if path_a.stat().st_size != size_b:
                    continue

                hash_a = self._get_file_hash(path_a)
                hash_b = self._get_file_hash(path_b)

                if hash_a and hash_b and hash_a == hash_b:
                    path_b.unlink()
                    duplicates.append(str(rel_path))
                    bytes_saved += size_b
                    logger.info(f"  [DELETED] {rel_path} (Duplicate found in Reference)")

            except Exception as e:
                logger.error(f"Error processing {path_b.name}: {e}")

        removed_dirs = 0
        for dirpath, _, _ in os.walk(folder_target, topdown=False):
            try:
                dp = Path(dirpath)
                if dp != folder_target and not any(dp.iterdir()):
                    dp.rmdir()
                    removed_dirs += 1
            except OSError:
                pass

        mb_saved = bytes_saved / (1024 * 1024)
        summary = (
            f"Duplicate Cleanup Complete.\n"
            f"Deleted {len(duplicates)} files.\n"
            f"Removed {removed_dirs} empty folders.\n"
            f"Saved: {mb_saved:.2f} MB."
        )
        logger.info(f"✅ {summary}")

        return {"summary": summary, "duplicates": duplicates}
