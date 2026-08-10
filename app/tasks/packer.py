from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.utils import atomic_write, normalize_path
from app.tasks.models import PackerResult, UnpackerResult

if TYPE_CHECKING:
    from collections.abc import Callable


class AssetPacker:
    def __init__(
        self,
        root_dir: Path,
        output_file: Path,
        extensions: tuple,
        progress_callback: Callable[[int, int], None] | None = None,
    ):
        self.root_dir = root_dir
        self.output_file = output_file
        self.extensions = extensions
        self.progress_callback = progress_callback

    def run(self) -> PackerResult:
        files = [p for p in self.root_dir.rglob("*") if p.is_file() and p.suffix.lower() in self.extensions]
        if not files:
            return PackerResult(summary="Packing failed: No files found.")

        try:
            with open(self.output_file, "w", encoding="utf-8", errors="ignore") as out:
                for i, f in enumerate(sorted(files), 1):
                    if self.progress_callback:
                        self.progress_callback(i, len(files))
                    rel = f.relative_to(self.root_dir)
                    header = f"===== FILE: {normalize_path(rel)} ====="

                    out.write(f"\n\n{header.center(80, '=')}\n\n")
                    out.write(f.read_text(encoding="utf-8", errors="ignore"))
        except Exception as e:
            return PackerResult(summary=f"Packing failed: {e}")

        return PackerResult(
            summary=f"Packed {len(files)} files into {self.output_file.name}.",
            packed_count=len(files),
        )


class AssetUnpacker:
    def __init__(
        self,
        input_file: Path,
        output_dir: Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ):
        self.input_file = input_file
        self.output_dir = output_dir
        self.progress_callback = progress_callback

    def run(self) -> UnpackerResult:
        if not self.input_file.is_file():
            return UnpackerResult(summary="File not found.")

        try:
            content = self.input_file.read_text(encoding="utf-8", errors="ignore")
            pattern = re.compile(r"={5,}\s*FILE:\s*(.*?)\s*={5,}\n\n(.*?)(?=\n\n={5,}\s*FILE:|\Z)", re.DOTALL)
            matches = pattern.findall(content)

            if not matches:
                return UnpackerResult(summary="No headers found.")

            for i, (rel, txt) in enumerate(matches, 1):
                if self.progress_callback:
                    self.progress_callback(i, len(matches))
                path = self.output_dir / Path(rel.strip())
                path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(path, txt.rstrip() + "\n", encoding="utf-8")
        except Exception as e:
            return UnpackerResult(summary=f"Unpacking failed: {e}")

        return UnpackerResult(summary=f"Unpacked {len(matches)} files.", unpacked_count=len(matches))
