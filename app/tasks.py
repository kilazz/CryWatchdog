# app/tasks.py
import logging
import os
import re
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import chardet

from app.config import AppConfig, CleanupStatus, LuaFileAnalysisResult
from app.utils import CoreSignals, atomic_write, find_files_by_extensions


def _cleaner_process_file_worker(file_path: Path, options: dict) -> tuple[CleanupStatus, str]:
    """Worker function for the project cleaner, processes a single file."""
    try:
        original_bytes = file_path.read_bytes()
        if not original_bytes:
            return CleanupStatus.SKIPPED, "File is empty"

        encoding = chardet.detect(original_bytes)["encoding"] or "utf-8"
        original_text = original_bytes.decode(encoding, errors="replace")
        processed_text, actions = original_text, []

        if (
            options.get("strip_bom")
            and file_path.suffix.lower() in AppConfig.XML_EXTENSIONS
            and (first_char_index := original_text.find("<")) > 0
        ):
            processed_text = original_text[first_char_index:]
            actions.append("stripped header")

        if any(options.get(k) for k in ["normalize_paths", "resolve_redundant_paths", "convert_to_lowercase"]):
            text_before = processed_text

            def processor(match: re.Match) -> str:
                key_eq, quote, path_content, comma_ws = match.groups()
                if "." not in path_content:
                    return match.group(0)

                modified_path = path_content
                if options.get("normalize_paths"):
                    modified_path = modified_path.replace("\\", "/")
                if options.get("resolve_redundant_paths"):
                    modified_path = os.path.normpath(modified_path).replace(os.path.sep, "/")
                if options.get("convert_to_lowercase"):
                    modified_path = modified_path.lower()
                return f"{key_eq}{quote}{modified_path}{quote}{comma_ws}"

            regex = re.compile(
                r"(\w+\s*=\s*)" + r'(["\'])' + r'([^"\']+\.[\w\d]+)' + r"\2" + r"(\s*,?\s*)",
                re.IGNORECASE,
            )
            processed_text = regex.sub(processor, processed_text)
            if processed_text != text_before:
                actions.append("cleaned paths")

        if options.get("trim_whitespace"):
            lines = processed_text.splitlines()
            processed_text = "\n".join([line.rstrip() for line in lines])
            if original_text and original_text.endswith(("\n", "\r")) and not processed_text.endswith(("\n", "\r")):
                processed_text += os.linesep
            if len(processed_text) != len(original_text):
                actions.append("trimmed whitespace")

        if not actions:
            return CleanupStatus.UNCHANGED, f"Already clean ({encoding})"

        final_encoding = encoding
        final_newline = None
        if options.get("normalize_encoding"):
            final_encoding = options.get("target_encoding", "utf-8")
            newline_map = {"CRLF (Windows)": "\r\n", "LF (Unix/macOS)": "\n", "CR (Classic Mac OS)": "\r"}
            final_newline = newline_map.get(options.get("newline_type_label"), "\r\n")
            newline_label = final_newline.replace("\r\n", "CRLF").replace("\n", "LF").replace("\r", "CR")
            actions.append(f"normalized to {final_encoding} ({newline_label})")

        atomic_write(file_path, processed_text, encoding=final_encoding, newline=final_newline)
        return CleanupStatus.MODIFIED, f"Cleaned ({', '.join(sorted(actions))})"
    except Exception as e:
        return CleanupStatus.ERROR, str(e)


class ProjectCleaner:
    """A task class for cleaning and normalizing all relevant project files."""

    def __init__(self, project_root: Path, signals: CoreSignals):
        self.project_root, self.signals = project_root, signals

    def run(self, **options: bool) -> dict:
        logging.info("=" * 30 + "\n🚀 Starting Project Cleanup Task...")
        start_time = time.time()
        files_to_process = find_files_by_extensions(self.project_root, tuple(AppConfig.HANDLED_TEXT_EXTENSIONS))
        if not files_to_process:
            return {"summary": "No target files found.", "failed_files": []}

        stats, failed_files = Counter(), []
        with ProcessPoolExecutor(max_workers=os.cpu_count() or 1) as executor:
            future_map = {executor.submit(_cleaner_process_file_worker, f, options): f for f in files_to_process}
            for i, future in enumerate(as_completed(future_map), 1):
                self.signals.progressUpdated.emit(i, len(files_to_process))
                file_path = future_map[future]
                try:
                    status, msg = future.result()
                    stats[status.name.lower()] += 1
                    if status == CleanupStatus.ERROR:
                        failed_files.append(f"{file_path.name}: {msg}")
                except Exception as e:
                    stats["error"] += 1
                    failed_files.append(f"{file_path.name}: Critical - {e}")

        duration = time.time() - start_time
        summary = (
            f"✅ Cleanup Task Complete in {duration:.2f}s.\n--- Summary ---\n"
            f"  Files modified: {stats['modified']}\n"
            f"  Files unchanged: {stats['unchanged']}\n"
            f"  Errors: {stats['error']}"
        )
        return {"summary": summary, "failed_files": failed_files}


class ProjectAnalyzer:
    """A task class for analyzing project file types and counts."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def run(self) -> dict:
        start_time = time.time()
        extensions_counter, total_files = Counter(), 0
        for _, _, files in os.walk(self.project_root):
            for filename in files:
                total_files += 1
                extensions_counter[os.path.splitext(filename)[1].lower() or ".<no_ext>"] += 1
        return {
            "total_files": total_files,
            "duration": time.time() - start_time,
            "extensions_counter": extensions_counter,
        }


class ProjectConverter:
    """A task class for converting all project filenames to lowercase."""

    def __init__(self, project_root: Path, signals: CoreSignals):
        self.project_root, self.signals = project_root, signals

    def run(self) -> dict:
        logging.info("=" * 50 + f"\n🔡 Starting filename conversion in '{self.project_root}' to lowercase...")
        renamed_count, error_count = 0, 0
        all_paths = list(self.project_root.rglob("*"))
        for i, path in enumerate(reversed(all_paths), 1):
            self.signals.progressUpdated.emit(i, len(all_paths))
            if path.name == path.name.lower():
                continue
            new_path = path.with_name(path.name.lower())
            if new_path.exists() and not path.samefile(new_path):
                logging.error(f"  - [FAIL] Conflict: '{new_path.name}' already exists. Skipping.")
                error_count += 1
                continue
            try:
                path.rename(new_path)
                logging.info(f"  - [OK] Renamed: {path.name} -> {new_path.name}")
                renamed_count += 1
            except OSError as e:
                logging.error(f"  - [FAIL] Could not rename {path.name}: {e}")
                error_count += 1
        summary = f"Conversion complete. Renamed {renamed_count} items with {error_count} errors."
        logging.info(f"✅ {summary}")
        return {"summary": summary}


class AssetPacker:
    """A task class for packing multiple text files into a single file."""

    def __init__(self, root_dir: Path, output_file: Path, extensions: tuple, signals: CoreSignals):
        self.root_dir, self.output_file, self.extensions, self.signals = root_dir, output_file, extensions, signals

    def run(self) -> dict:
        files_to_pack = [p for p in self.root_dir.rglob("*") if p.is_file() and p.suffix.lower() in self.extensions]
        if not files_to_pack:
            return {"summary": "Packing failed: No matching files found."}
        try:
            with open(self.output_file, "w", encoding="utf-8", errors="ignore") as outfile:
                for i, file_path in enumerate(sorted(files_to_pack), 1):
                    self.signals.progressUpdated.emit(i, len(files_to_pack))
                    relative_path = file_path.relative_to(self.root_dir)
                    header = f"===== FILE: {str(relative_path).replace(os.path.sep, '/')} ====="
                    outfile.write(f"\n\n{header.center(80, '=')}\n\n")
                    outfile.write(file_path.read_text(encoding="utf-8", errors="ignore"))
        except Exception as e:
            return {"summary": f"Packing failed: {e}"}
        return {"summary": f"Packed {len(files_to_pack)} files into {self.output_file.name}."}


class AssetUnpacker:
    """A task class for unpacking a single archive file back into multiple files."""

    def __init__(self, input_file: Path, output_dir: Path, signals: CoreSignals):
        self.input_file, self.output_dir, self.signals = input_file, output_dir, signals

    def run(self) -> dict:
        if not self.input_file.is_file():
            return {"summary": "Unpacking failed: Source file not found."}
        try:
            content = self.input_file.read_text(encoding="utf-8", errors="ignore")
            pattern = re.compile(r"={5,}\s*FILE:\s*(.*?)\s*={5,}\n\n(.*?)(?=\n\n={5,}\s*FILE:|\Z)", re.DOTALL)
            matches = pattern.findall(content)
            if not matches:
                return {"summary": "Unpacking failed: No valid file headers found."}

            for i, (rel_path_str, file_content) in enumerate(matches, 1):
                self.signals.progressUpdated.emit(i, len(matches))
                full_output_path = self.output_dir / Path(rel_path_str.strip())
                full_output_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(full_output_path, file_content.rstrip() + "\n", encoding="utf-8")
        except Exception as e:
            return {"summary": f"Unpacking failed: {e}"}
        return {"summary": f"Unpacked {len(matches)} files from {self.input_file.name}."}


class LuaToolkit:
    """A task class providing diagnostics and formatting for Lua files."""

    def __init__(self, project_root: Path, signals: CoreSignals):
        self.project_root, self.signals = project_root, signals
        self.luac_path, self.stylua_path = None, None
        self._find_executables()

    def _find_executables(self):
        """Finds luac and stylua executables."""
        script_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        if (luac := script_dir / AppConfig.LUA_COMPILER_EXE_NAME).is_file():
            self.luac_path = luac
        if (stylua := script_dir / AppConfig.STYLUO_EXE_NAME).is_file():
            self.stylua_path = stylua

    def _run_command(self, command: list[str]) -> tuple[bool, str]:
        """Runs an external command and captures its output."""
        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=60,
                check=False,
                creationflags=creation_flags,
            )
            return proc.returncode == 0, (proc.stderr or proc.stdout or "").strip()
        except Exception as e:
            return False, f"Exception: {e}"

    def _check_encoding(self, file_path: Path) -> str:
        """Determines the encoding of a file."""
        try:
            content = file_path.read_bytes()
            if content.startswith(b"\xef\xbb\xbf"):
                return "UTF-8-SIG"
            content.decode("utf-8")
            return "UTF-8"
        except UnicodeDecodeError:
            return chardet.detect(content[:4096])["encoding"] or "Unknown"
        except Exception:
            return "Read Error"

    def run_diagnostics(self) -> list[LuaFileAnalysisResult]:
        """Runs syntax and encoding checks on all .lua files in the project."""
        logging.info("=" * 50 + "\n📊 Starting Lua Diagnostics Task...")
        if not self.luac_path:
            logging.error(f"{AppConfig.LUA_COMPILER_EXE_NAME} not found.")
            return []
        lua_files = list(self.project_root.rglob("*.lua"))
        if not lua_files:
            return []

        results = []
        for i, file_path in enumerate(lua_files, 1):
            self.signals.progressUpdated.emit(i, len(lua_files))
            relative_path = file_path.relative_to(self.project_root).as_posix()
            if AppConfig.INVALID_PATH_CHARS_RE.search(str(file_path)):
                results.append(
                    LuaFileAnalysisResult(
                        relative_path, False, "Path contains invalid characters.", "N/A", "path_error"
                    )
                )
                continue

            is_ok, msg = self._run_command([str(self.luac_path), "-p", str(file_path)])
            encoding = self._check_encoding(file_path)
            status = "syntax_error" if not is_ok else "encoding_issue" if "UTF-8" not in encoding else "ok"
            if status != "ok":
                results.append(LuaFileAnalysisResult(relative_path, is_ok, msg or "OK", encoding, status))
        logging.info("✅ Lua diagnostics complete.")
        return results

    def run_formatting(self, config: dict) -> dict:
        """Formats all .lua files using stylua with the given configuration."""
        logging.info("=" * 50 + "\n💅 Starting Lua Formatting Task...")
        if not self.stylua_path:
            return {"summary": "Formatting failed: stylua.exe not found."}

        lua_files = [str(p) for p in self.project_root.rglob("*.lua")]
        if not lua_files:
            return {"summary": "No .lua files found to format."}

        base_command = [str(self.stylua_path), "--no-editorconfig"]
        for key, value in config.items():
            cli_key = f"--{key.replace('_', '-')}"
            base_command.extend([cli_key, str(value).lower()])

        is_ok, message = self._run_command(base_command + lua_files)
        if not is_ok:
            logging.error(f"Formatting command failed. Error: {message}")
            return {"summary": "Formatting task failed. See log for details."}

        # Extract summary from stylua's output
        formatted_match = re.search(r"Formatted (\d+) files", message)
        unchanged_match = re.search(r"Unchanged (\d+) files", message)
        formatted = int(formatted_match.group(1)) if formatted_match else 0
        unchanged = int(unchanged_match.group(1)) if unchanged_match else 0
        summary = f"Formatting complete. Formatted: {formatted}, Unchanged: {unchanged}."
        logging.info(f"✅ {summary}")
        return {"summary": summary}
