# app/tasks.py
import logging
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import chardet

from app.asset_handlers import ASSET_HANDLERS
from app.config import AppConfig, CleanupStatus, LuaFileAnalysisResult
from app.utils import CoreSignals, atomic_write, find_files_by_extensions


def _cleaner_process_file_worker(file_path: Path, options: dict) -> tuple[CleanupStatus, str]:
    """
    Worker function for the project cleaner.

    Optimized to assume UTF-8 first (speed), falling back to chardet (accuracy)
    only if decoding fails.
    """
    try:
        # 1. Read raw bytes
        original_bytes = file_path.read_bytes()
        if not original_bytes:
            return CleanupStatus.SKIPPED, "File is empty"

        # 2. Detect encoding (Optimistic approach)
        # Try UTF-8 first (covers 95%+ of modern assets), fall back to chardet only on error.
        encoding = "utf-8"
        try:
            original_text = original_bytes.decode("utf-8")
        except UnicodeDecodeError:
            detected = chardet.detect(original_bytes)
            encoding = detected["encoding"] or "utf-8"
            original_text = original_bytes.decode(encoding, errors="replace")

        processed_text = original_text
        actions = []

        # --- Step A: Content Logic (BOM, Paths, Trimming) ---

        # A.1 Strip BOM / Header
        if (
            options.get("strip_bom")
            and file_path.suffix.lower() in AppConfig.XML_EXTENSIONS
            and (first_char_index := processed_text.find("<")) > 0
        ):
            processed_text = processed_text[first_char_index:]
            actions.append("stripped header")

        # A.2 Path & String Normalization
        if any(options.get(k) for k in ["normalize_paths", "resolve_redundant_paths", "convert_to_lowercase"]):
            text_before_paths = processed_text

            def processor(match: re.Match) -> str:
                key_eq, quote, path_content, comma_ws = match.groups()
                # Skip non-file strings (must have extension)
                if "." not in path_content:
                    return match.group(0)

                modified_path = path_content

                if options.get("normalize_paths"):
                    modified_path = modified_path.replace("\\", "/")

                if options.get("resolve_redundant_paths"):
                    # e.g. "textures/../objects/file.cgf" -> "objects/file.cgf"
                    modified_path = os.path.normpath(modified_path).replace(os.path.sep, "/")

                if options.get("convert_to_lowercase"):
                    modified_path = modified_path.lower()

                return f"{key_eq}{quote}{modified_path}{quote}{comma_ws}"

            # Regex to find "Key='Value'" patterns
            regex = re.compile(
                r"(\w+\s*=\s*)" + r'(["\'])' + r'([^"\']+\.[\w\d]+)' + r"\2" + r"(\s*,?\s*)",
                re.IGNORECASE,
            )
            processed_text = regex.sub(processor, processed_text)
            if processed_text != text_before_paths:
                actions.append("cleaned paths")

        # A.3 Trim Whitespace
        if options.get("trim_whitespace"):
            lines = processed_text.splitlines()
            # Join with generic newline temporarily
            trimmed_text = "\n".join([line.rstrip() for line in lines])

            # Restore trailing newline if original had it
            if original_text and original_text.endswith(("\n", "\r")) and not trimmed_text.endswith("\n"):
                trimmed_text += "\n"

            # Check if content changed (ignoring line ending differences for now)
            if trimmed_text.replace("\n", "") != processed_text.replace("\r", "").replace("\n", ""):
                actions.append("trimmed whitespace")

            processed_text = trimmed_text

        # --- Step B: Encoding & Line Endings ---

        final_encoding = encoding
        final_newline = None

        if options.get("normalize_encoding"):
            final_encoding = options.get("target_encoding", "utf-8")

            newline_map = {
                "CRLF (Windows)": "\r\n",
                "LF (Unix/macOS)": "\n",
                "CR (Classic Mac OS)": "\r",
            }
            # Default to CRLF if not specified
            label = options.get("newline_type_label")
            final_newline = newline_map.get(label, "\r\n")

            # 1. Normalize in-memory text to pure \n first (Python internal state)
            processed_text_lf = processed_text.replace("\r\n", "\n").replace("\r", "\n")

            # 2. Simulate the bytes that WILL be written to disk to check for changes
            # We explicitly replace \n with the target newline to mimic file writing
            text_for_comparison = processed_text_lf.replace("\n", final_newline)

            try:
                new_bytes = text_for_comparison.encode(final_encoding)
            except Exception:
                # If encoding fails during check, assume modified to be safe
                new_bytes = None

            # 3. Compare bytes. Only flag as "modified" if bytes are different
            # AND we haven't already flagged modification in Step A.
            if new_bytes is not None and new_bytes != original_bytes and not actions:
                actions.append(f"normalized to {final_encoding} / {label}")

            # Update the text variable for the final write
            processed_text = processed_text_lf

        # --- Final Decision ---

        # If the 'actions' list is empty, it means:
        # 1. No content logic (paths/trim) triggered.
        # 2. The byte comparison showed the file on disk is ALREADY exactly what we want.
        if not actions:
            return CleanupStatus.UNCHANGED, f"Already clean ({encoding})"

        # Write to disk
        # Note: atomic_write with text uses open(..., newline=final_newline)
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

        stats = Counter()
        failed_files = []

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

            # Case-insensitive FS collision check
            if new_path.exists() and not path.samefile(new_path):
                logging.error(f"  - [FAIL] Conflict: '{new_path.name}' already exists. Skipping.")
                error_count += 1
                continue

            try:
                # Note: On P4/Git driven repos, renaming usually requires specific commands.
                # This is a simple OS rename.
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
        script_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        if (luac := script_dir / AppConfig.LUA_COMPILER_EXE_NAME).is_file():
            self.luac_path = luac
        if (stylua := script_dir / AppConfig.STYLUO_EXE_NAME).is_file():
            self.stylua_path = stylua

    def _run_command(self, command: list[str]) -> tuple[bool, str]:
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

        formatted_match = re.search(r"Formatted (\d+) files", message)
        unchanged_match = re.search(r"Unchanged (\d+) files", message)
        formatted = int(formatted_match.group(1)) if formatted_match else 0
        unchanged = int(unchanged_match.group(1)) if unchanged_match else 0

        summary = f"Formatting complete. Formatted: {formatted}, Unchanged: {unchanged}."
        logging.info(f"✅ {summary}")
        return {"summary": summary}


def _finder_parse_wrapper(file_path: Path) -> set[str]:
    """Static wrapper to call handlers, used by ProcessPoolExecutor."""
    Handler = ASSET_HANDLERS.get(file_path.suffix.lower())
    if Handler:
        return Handler.parse(file_path)
    return set()


class UnusedAssetFinder:
    """
    Task to find 'Orphaned' assets - files that exist on disk
    but are not referenced by any material, level, or script.
    """

    def __init__(self, project_root: Path, signals: CoreSignals):
        self.project_root = project_root
        self.signals = signals

    def run(self) -> dict:
        logging.info("=" * 30 + "\n🔍 Starting Unused Asset Scan...")
        start_time = time.time()

        # 1. Index all files on disk
        all_assets_stems = set()
        asset_map = {}  # stem -> relative_path
        container_files = []

        # Extensions we consider "Assets" (Textures, Models)
        asset_exts = AppConfig.TEXTURE_EXTENSIONS.union({".cgf", ".cga", ".chr", ".skin"})

        # Extensions we parse for references
        container_exts = set(ASSET_HANDLERS.keys())

        logging.info("Indexing filesystem...")
        for root, _, files in os.walk(self.project_root):
            for f in files:
                path = Path(root) / f
                ext = path.suffix.lower()
                rel_path = path.relative_to(self.project_root).as_posix()

                if ext in asset_exts:
                    # Store both full path and a normalized 'stem path' for fuzzy matching
                    stem_path = Path(rel_path).with_suffix("").as_posix().lower()
                    all_assets_stems.add(stem_path)
                    asset_map[stem_path] = rel_path

                if ext in container_exts:
                    container_files.append(path)

        logging.info(f"Found {len(all_assets_stems)} unique asset stems and {len(container_files)} containers.")

        # 2. Parse all containers to find references (Multi-threaded)
        referenced_stems = set()
        processed_count = 0

        with ProcessPoolExecutor(max_workers=os.cpu_count() or 1) as executor:
            future_map = {executor.submit(_finder_parse_wrapper, f): f for f in container_files}

            for future in as_completed(future_map):
                processed_count += 1
                if processed_count % 50 == 0:
                    self.signals.progressUpdated.emit(processed_count, len(container_files))

                found_refs = future.result()
                for ref in found_refs:
                    ref_stem = Path(ref).with_suffix("").as_posix().lower()
                    referenced_stems.add(ref_stem)

        # 3. Calculate Difference (Assets - References)
        unused_assets = []

        logging.info("Analyzing usage...")
        for stem in all_assets_stems:
            if stem not in referenced_stems:
                unused_assets.append(asset_map[stem])

        duration = time.time() - start_time
        summary = f"Scan Complete. Found {len(unused_assets)} unused assets."
        logging.info(f"✅ {summary}")

        return {
            "summary": summary,
            "unused_files": sorted(unused_assets),
            "total_assets": len(all_assets_stems),
            "duration": duration,
        }


class MissingAssetFinder:
    """
    Task to find 'Broken References' - files referenced in materials/scripts
    that do not exist on the disk.
    Includes smart logic to handle virtual path duplication (e.g. EngineAssets/EngineAssets).
    """

    def __init__(self, project_root: Path, signals: CoreSignals):
        self.project_root = project_root
        self.signals = signals

    def run(self) -> dict:
        logging.info("=" * 30 + "\n🔍 Starting Broken Reference Scan...")
        start_time = time.time()

        # 1. Identify container files (files that can contain references)
        container_exts = tuple(ASSET_HANDLERS.keys())
        container_files = find_files_by_extensions(self.project_root, container_exts)

        if not container_files:
            return {"summary": "No container files found to scan.", "missing_map": {}}

        # 2. Parse files in parallel to find all references
        # Structure: { "missing/path/texture.dds": ["found_in_mat.mtl", "found_in_level.lyr"] }
        missing_map = defaultdict(list)

        # We cache file existence checks to avoid hitting OS too often for common assets
        # (e.g. strict_check_cache["textures/default.dds"] = True)
        existence_cache = {}

        logging.info(f"Scanning {len(container_files)} files for broken links...")

        with ProcessPoolExecutor(max_workers=os.cpu_count() or 1) as executor:
            future_map = {executor.submit(_finder_parse_wrapper, f): f for f in container_files}

            for i, future in enumerate(as_completed(future_map), 1):
                self.signals.progressUpdated.emit(i, len(container_files))
                container_path = future_map[future]

                try:
                    referenced_paths = future.result()
                except Exception as e:
                    logging.warning(f"Failed to parse {container_path.name}: {e}")
                    continue

                container_rel = container_path.relative_to(self.project_root).as_posix()

                for ref in referenced_paths:
                    # Logic: Refs are strictly checked relative to project root.

                    if ref in existence_cache:
                        exists = existence_cache[ref]
                    else:
                        # Prepare candidates to check.
                        # 1. Exact path
                        candidates = [ref]

                        # 2. Smart Deduplication candidate:
                        # If project root is "EngineAssets" and ref is "EngineAssets/Textures/...",
                        # also check "Textures/..."
                        ref_parts = Path(ref).parts
                        if len(ref_parts) > 1 and ref_parts[0].lower() == self.project_root.name.lower():
                            candidates.append(Path(*ref_parts[1:]).as_posix())

                        exists = False

                        # Check all candidates
                        for candidate in candidates:
                            # Direct check
                            if (self.project_root / candidate).exists():
                                exists = True
                                break

                            # Fuzzy Check: If .tif referenced, check if .dds exists
                            if candidate.lower().endswith((".tif", ".tiff", ".png", ".tga")):
                                dds_candidate = Path(candidate).with_suffix(".dds").as_posix()
                                if (self.project_root / dds_candidate).exists():
                                    exists = True
                                    break

                        # Cache the result for the original reference string
                        existence_cache[ref] = exists

                    if not exists:
                        missing_map[ref].append(container_rel)

        duration = time.time() - start_time
        missing_count = len(missing_map)
        summary = f"Scan Complete. Found {missing_count} missing assets referenced in project."

        logging.info(f"✅ {summary}")

        return {
            "summary": summary,
            "missing_map": dict(missing_map),
            "duration": duration,
            "total_scanned": len(container_files),
        }
