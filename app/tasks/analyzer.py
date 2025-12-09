# app/tasks/analyzer.py
import os
import time
from collections import Counter
from pathlib import Path


class ProjectAnalyzer:
    """A task class for analyzing project file types and counts."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def run(self) -> dict:
        start_time = time.time()
        extensions_counter = Counter()
        total_files = 0

        try:
            for _, _, files in os.walk(self.project_root):
                for filename in files:
                    total_files += 1
                    # Extract extension or use a placeholder for files without one
                    ext = os.path.splitext(filename)[1].lower()
                    if not ext:
                        ext = ".<no_ext>"
                    extensions_counter[ext] += 1

        except Exception as e:
            # If an error occurs (e.g., PermissionError), return what we have so far
            # plus the error message.
            return {
                "total_files": total_files,
                "duration": time.time() - start_time,
                "extensions_counter": extensions_counter,
                "error": str(e),
            }

        return {
            "total_files": total_files,
            "duration": time.time() - start_time,
            "extensions_counter": extensions_counter,
        }
