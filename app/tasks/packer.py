# app/tasks/packer.py
import os
import re
from pathlib import Path

from app.core.utils import atomic_write


class AssetPacker:
    def __init__(self, root_dir: Path, output_file: Path, extensions: tuple, signals):
        self.root_dir, self.output_file, self.extensions, self.signals = root_dir, output_file, extensions, signals

    def run(self) -> dict:
        files = [p for p in self.root_dir.rglob("*") if p.is_file() and p.suffix.lower() in self.extensions]
        if not files:
            return {"summary": "Packing failed: No files found."}
        try:
            with open(self.output_file, "w", encoding="utf-8", errors="ignore") as out:
                for i, f in enumerate(sorted(files), 1):
                    self.signals.progressUpdated.emit(i, len(files))
                    rel = f.relative_to(self.root_dir)
                    header = f"===== FILE: {str(rel).replace(os.path.sep, '/')} ====="
                    out.write(f"\n\n{header.center(80, '=')}\n\n")
                    out.write(f.read_text(encoding="utf-8", errors="ignore"))
        except Exception as e:
            return {"summary": f"Packing failed: {e}"}
        return {"summary": f"Packed {len(files)} files into {self.output_file.name}."}


class AssetUnpacker:
    def __init__(self, input_file: Path, output_dir: Path, signals):
        self.input_file, self.output_dir, self.signals = input_file, output_dir, signals

    def run(self) -> dict:
        if not self.input_file.is_file():
            return {"summary": "File not found."}
        try:
            content = self.input_file.read_text(encoding="utf-8", errors="ignore")
            pattern = re.compile(r"={5,}\s*FILE:\s*(.*?)\s*={5,}\n\n(.*?)(?=\n\n={5,}\s*FILE:|\Z)", re.DOTALL)
            matches = pattern.findall(content)
            if not matches:
                return {"summary": "No headers found."}
            for i, (rel, txt) in enumerate(matches, 1):
                self.signals.progressUpdated.emit(i, len(matches))
                path = self.output_dir / Path(rel.strip())
                path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(path, txt.rstrip() + "\n", encoding="utf-8")
        except Exception as e:
            return {"summary": f"Unpacking failed: {e}"}
        return {"summary": f"Unpacked {len(matches)} files."}
