# app/tasks/duplicates.py
import hashlib
import logging
import os
from pathlib import Path


class DuplicateFinder:
    """
    Task to find and delete files in a Target folder that are bit-exact duplicates
    of files in a Reference folder (same relative path + same content).
    """

    def __init__(self, signals):
        self.signals = signals

    def _get_file_hash(self, filepath: Path) -> str | None:
        """Calculates MD5 hash of a file efficiently."""
        hasher = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logging.warning(f"Could not hash {filepath}: {e}")
            return None

    def run(self, folder_ref: Path, folder_target: Path) -> dict:
        logging.info(f"Starting Duplicate Scan.\n  Reference: {folder_ref}\n  Target: {folder_target}")

        if folder_ref == folder_target:
            return {"summary": "Error: Reference and Target folders cannot be the same."}

        duplicates = []
        bytes_saved = 0

        # Gather all files in the target directory
        target_files = [p for p in folder_target.rglob("*") if p.is_file()]
        total_files = len(target_files)

        logging.info(f"Scanning {total_files} files in target against reference...")

        for i, path_b in enumerate(target_files, 1):
            if i % 10 == 0:
                self.signals.progressUpdated.emit(i, total_files)

            try:
                # Determine the relative path (e.g., "Textures/wood.dds")
                rel_path = path_b.relative_to(folder_target)
                path_a = folder_ref / rel_path

                # 1. Existence Check: Does the file exist in the reference folder?
                if not path_a.exists():
                    continue

                # 2. Size Check: Are files the same size? (Fast)
                size_b = path_b.stat().st_size
                if path_a.stat().st_size != size_b:
                    continue

                # 3. Hash Check: Are contents identical? (Slow, but accurate)
                hash_a = self._get_file_hash(path_a)
                hash_b = self._get_file_hash(path_b)

                if hash_a and hash_b and hash_a == hash_b:
                    # Delete the duplicate from Target
                    path_b.unlink()
                    duplicates.append(str(rel_path))
                    bytes_saved += size_b
                    logging.info(f"  [DELETED] {rel_path} (Duplicate found in Reference)")

            except Exception as e:
                logging.error(f"Error processing {path_b.name}: {e}")

        # Clean up empty directories in Target after deletion
        removed_dirs = 0
        for dirpath, _, _ in os.walk(folder_target, topdown=False):
            try:
                dp = Path(dirpath)
                # Ensure we don't delete the root target folder, only subfolders
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
        logging.info(f"✅ {summary}")

        return {"summary": summary, "duplicates": duplicates}
