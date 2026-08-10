from __future__ import annotations

import os
import time
from collections import Counter
from typing import TYPE_CHECKING

from app.tasks.models import AnalyzerResult

if TYPE_CHECKING:
    from pathlib import Path


class ProjectAnalyzer:
    def __init__(self, project_root: Path):
        self.project_root = project_root

    def run(self) -> AnalyzerResult:
        start_time = time.time()
        extensions_counter: Counter[str] = Counter()
        total_files = 0

        try:
            for _, _, files in os.walk(self.project_root):
                for filename in files:
                    total_files += 1
                    ext = os.path.splitext(filename)[1].lower() or ".<no_ext>"
                    extensions_counter[ext] += 1

        except Exception as e:
            return AnalyzerResult(
                total_files=total_files,
                duration=time.time() - start_time,
                extensions_counter=extensions_counter,
                error=str(e),
            )

        return AnalyzerResult(
            total_files=total_files,
            duration=time.time() - start_time,
            extensions_counter=extensions_counter,
        )
