# app/tasks/cleaner.py
import os
import re
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import chardet

from app.config import AppConfig, CleanupStatus
from app.core.utils import atomic_write, find_files_by_extensions


def _cleaner_process_file_worker(file_path: Path, options: dict) -> tuple[CleanupStatus, str]:
    try:
        original_bytes = file_path.read_bytes()
        if not original_bytes:
            return CleanupStatus.SKIPPED, "File is empty"

        encoding = "utf-8"
        try:
            original_text = original_bytes.decode("utf-8")
        except UnicodeDecodeError:
            detected = chardet.detect(original_bytes)
            encoding = detected["encoding"] or "utf-8"
            original_text = original_bytes.decode(encoding, errors="replace")

        processed_text = original_text
        actions = []

        if (
            options.get("strip_bom")
            and file_path.suffix.lower() in AppConfig.XML_EXTENSIONS
            and (first_char_index := processed_text.find("<")) > 0
        ):
            processed_text = processed_text[first_char_index:]
            actions.append("stripped header")

        if any(options.get(k) for k in ["normalize_paths", "resolve_redundant_paths", "convert_to_lowercase"]):
            text_before_paths = processed_text

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
            if processed_text != text_before_paths:
                actions.append("cleaned paths")

        if options.get("trim_whitespace"):
            lines = processed_text.splitlines()
            trimmed_text = "\n".join([line.rstrip() for line in lines])
            if original_text and original_text.endswith(("\n", "\r")) and not trimmed_text.endswith("\n"):
                trimmed_text += "\n"
            if trimmed_text.replace("\n", "") != processed_text.replace("\r", "").replace("\n", ""):
                actions.append("trimmed whitespace")
            processed_text = trimmed_text

        final_encoding = encoding
        final_newline = None

        if options.get("normalize_encoding"):
            final_encoding = options.get("target_encoding", "utf-8")
            newline_map = {
                "CRLF (Windows)": "\r\n",
                "LF (Unix/macOS)": "\n",
                "CR (Classic Mac OS)": "\r",
            }
            label = options.get("newline_type_label")
            final_newline = newline_map.get(label, "\r\n")

            processed_text_lf = processed_text.replace("\r\n", "\n").replace("\r", "\n")
            text_for_comparison = processed_text_lf.replace("\n", final_newline)
            try:
                new_bytes = text_for_comparison.encode(final_encoding)
            except Exception:
                new_bytes = None
            if new_bytes is not None and new_bytes != original_bytes and not actions:
                actions.append(f"normalized to {final_encoding} / {label}")
            processed_text = processed_text_lf

        if not actions:
            return CleanupStatus.UNCHANGED, f"Already clean ({encoding})"

        atomic_write(file_path, processed_text, encoding=final_encoding, newline=final_newline)
        return CleanupStatus.MODIFIED, f"Cleaned ({', '.join(sorted(actions))})"

    except Exception as e:
        return CleanupStatus.ERROR, str(e)


class ProjectCleaner:
    def __init__(self, project_root: Path, signals):
        self.project_root, self.signals = project_root, signals

    def run(self, **options: bool) -> dict:
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
