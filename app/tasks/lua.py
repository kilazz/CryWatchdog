from __future__ import annotations

import logging
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from app.config import AppConfig, LuaFileAnalysisResult

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class LuaToolkit:
    def __init__(self, root: Path, signals):
        self.root = root
        self.signals = signals
        self.luac = AppConfig.LUA_COMPILER_PATH
        self.stylua = AppConfig.STYLUA_PATH

    def _run_cmd(self, cmd: list[str]) -> tuple[bool, str]:
        cmd_str = " ".join(cmd[:3]) + ("..." if len(cmd) > 3 else "")
        logger.debug(f"Running command: {cmd_str}")

        try:
            flags = 0x08000000 if sys.platform == "win32" else 0

            p = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=60,
                creationflags=flags,
            )

            output = (p.stderr or p.stdout or "").strip()

            if p.returncode != 0:
                logger.debug(f"Command failed (Code {p.returncode}). Output: {output[:200]}")

            return p.returncode == 0, output

        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {cmd_str}")
            return False, "Timeout expired"
        except Exception as e:
            logger.exception(f"Exception running command: {cmd_str}")
            return False, f"Execution Error: {e!s}"

    def _check_single_file(self, file_path: Path) -> LuaFileAnalysisResult:
        try:
            rel_path = file_path.relative_to(self.root).as_posix()
        except ValueError:
            rel_path = file_path.name

        is_ok, msg = self._run_cmd([str(self.luac), "-p", str(file_path)])
        status = "ok" if is_ok else "syntax_error"

        if not is_ok and "Execution Error" in msg:
            logger.warning(f"Lua Tool Failure for {file_path.name}: {msg}")

        return LuaFileAnalysisResult(
            relative_path=rel_path, is_syntax_ok=is_ok, message=msg, encoding="UTF-8", status=status
        )

    def run_diagnostics(self) -> list[LuaFileAnalysisResult]:
        if not self.luac.is_file():
            logger.error(f"Lua Compiler not found at: {self.luac}")
            return []

        try:
            files = list(self.root.rglob("*.lua"))
        except Exception:
            logger.exception("Failed to scan for .lua files")
            return []

        if not files:
            logger.info("No Lua files found to diagnose.")
            return []

        results = []
        max_workers = min(32, (os.cpu_count() or 1) * 4)

        logger.info(f"Starting Lua diagnostics on {len(files)} files with {max_workers} threads...")

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {executor.submit(self._check_single_file, f): f for f in files}

                for i, future in enumerate(as_completed(future_map), 1):
                    if i % 10 == 0 or i == len(files):
                        self.signals.progressUpdated.emit(i, len(files))

                    try:
                        results.append(future.result())
                    except Exception as e:
                        f_name = future_map[future]
                        logger.error(f"Thread failed for {f_name}: {e}")

        except Exception:
            logger.exception("Critical error in diagnostic thread pool")
            return results

        logger.info(f"Diagnostics finished. Processed {len(results)} files.")
        return results

    def run_formatting(self, config: dict) -> dict:
        if not self.stylua.is_file():
            return {"summary": f"Stylua not found at: {self.stylua}"}

        try:
            files = [str(p) for p in self.root.rglob("*.lua")]
        except Exception as e:
            logger.error(f"Error scanning for files: {e}")
            return {"summary": f"Error scanning for files: {e}"}

        if not files:
            return {"summary": "No Lua files found."}

        base_cmd = [str(self.stylua), "--no-editorconfig"]
        for k, v in config.items():
            base_cmd.extend([f"--{k.replace('_', '-')}", str(v).lower()])

        CHUNK_SIZE = 50
        total_chunks = math.ceil(len(files) / CHUNK_SIZE)

        failed_chunks = 0
        last_error = ""

        logger.info(f"Formatting {len(files)} files in {total_chunks} batches...")

        for i in range(0, len(files), CHUNK_SIZE):
            chunk = files[i : i + CHUNK_SIZE]

            self.signals.progressUpdated.emit(min(i + CHUNK_SIZE, len(files)), len(files))
            logger.debug(f"Formatting batch {i // CHUNK_SIZE + 1}/{total_chunks}...")

            is_ok, msg = self._run_cmd(base_cmd + chunk)

            if not is_ok:
                failed_chunks += 1
                last_error = msg
                logger.warning(f"Formatting batch failed: {msg}")

        if failed_chunks == 0:
            return {"summary": "Formatting complete."}
        else:
            return {
                "summary": f"Formatting completed with errors in {failed_chunks} batches.\nLast error: {last_error}"
            }
