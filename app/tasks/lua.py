# app/tasks/lua.py
import logging
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.config import AppConfig, LuaFileAnalysisResult


class LuaToolkit:
    """
    A task class providing diagnostics (using luac) and formatting (using Stylua).
    Uses ThreadPoolExecutor for parallel processing to prevent UI freezes.
    """

    def __init__(self, root: Path, signals):
        self.root = root
        self.signals = signals
        self.luac = AppConfig.LUA_COMPILER_PATH
        self.stylua = AppConfig.STYLUA_PATH

    def _run_cmd(self, cmd: list[str]) -> tuple[bool, str]:
        """Helper to run a subprocess command safely with detailed logging."""
        # Log the command (truncated) for debugging
        cmd_str = " ".join(cmd[:3]) + ("..." if len(cmd) > 3 else "")
        logging.debug(f"Running command: {cmd_str}")

        try:
            # CREATE_NO_WINDOW is needed on Windows to prevent a console window flashing
            flags = 0x08000000 if sys.platform == "win32" else 0

            p = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=60,  # Generous timeout to prevent hanging
                creationflags=flags,
            )

            output = (p.stderr or p.stdout or "").strip()

            if p.returncode != 0:
                logging.debug(f"Command failed (Code {p.returncode}). Output: {output[:200]}")

            return p.returncode == 0, output

        except subprocess.TimeoutExpired:
            logging.error(f"Command timed out: {cmd_str}")
            return False, "Timeout expired"
        except Exception as e:
            logging.exception(f"Exception running command: {cmd_str}")
            return False, f"Execution Error: {e!s}"

    def _check_single_file(self, file_path: Path) -> LuaFileAnalysisResult:
        """Worker function to check a single Lua file."""
        try:
            rel_path = file_path.relative_to(self.root).as_posix()
        except ValueError:
            rel_path = file_path.name

        is_ok, msg = self._run_cmd([str(self.luac), "-p", str(file_path)])
        status = "ok" if is_ok else "syntax_error"

        if not is_ok and "Execution Error" in msg:
            logging.warning(f"Lua Tool Failure for {file_path.name}: {msg}")

        return LuaFileAnalysisResult(
            relative_path=rel_path, is_syntax_ok=is_ok, message=msg, encoding="UTF-8", status=status
        )

    def run_diagnostics(self) -> list[LuaFileAnalysisResult]:
        """Checks Lua files for syntax errors using parallel execution."""
        if not self.luac.is_file():
            logging.error(f"Lua Compiler not found at: {self.luac}")
            return []

        try:
            files = list(self.root.rglob("*.lua"))
        except Exception:
            logging.exception("Failed to scan for .lua files")
            return []

        if not files:
            logging.info("No Lua files found to diagnose.")
            return []

        results = []

        # Determine number of worker threads (IO/Process bound mix)
        # Cap at 32 to avoid overhead on systems with huge core counts
        max_workers = min(32, (os.cpu_count() or 1) * 4)

        logging.info(f"Starting Lua diagnostics on {len(files)} files with {max_workers} threads...")

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {executor.submit(self._check_single_file, f): f for f in files}

                for i, future in enumerate(as_completed(future_map), 1):
                    # Update progress sparingly to avoid flooding the UI signal queue
                    if i % 10 == 0 or i == len(files):
                        self.signals.progressUpdated.emit(i, len(files))

                    try:
                        results.append(future.result())
                    except Exception as e:
                        f_name = future_map[future]
                        logging.error(f"Thread failed for {f_name}: {e}")

        except Exception:
            logging.exception("Critical error in diagnostic thread pool")
            return results

        logging.info(f"Diagnostics finished. Processed {len(results)} files.")
        return results

    def run_formatting(self, config: dict) -> dict:
        """Formats Lua files using StyLua (Batched to avoid CLI length limits)."""
        if not self.stylua.is_file():
            return {"summary": f"Stylua not found at: {self.stylua}"}

        try:
            files = [str(p) for p in self.root.rglob("*.lua")]
        except Exception as e:
            logging.error(f"Error scanning for files: {e}")
            return {"summary": f"Error scanning for files: {e}"}

        if not files:
            return {"summary": "No Lua files found."}

        base_cmd = [str(self.stylua), "--no-editorconfig"]
        for k, v in config.items():
            base_cmd.extend([f"--{k.replace('_', '-')}", str(v).lower()])

        # Windows command line limit is ~8191 characters.
        # We process files in chunks to avoid this limit.
        CHUNK_SIZE = 50
        total_chunks = math.ceil(len(files) / CHUNK_SIZE)

        failed_chunks = 0
        last_error = ""

        logging.info(f"Formatting {len(files)} files in {total_chunks} batches...")

        for i in range(0, len(files), CHUNK_SIZE):
            chunk = files[i : i + CHUNK_SIZE]

            self.signals.progressUpdated.emit(min(i + CHUNK_SIZE, len(files)), len(files))
            logging.debug(f"Formatting batch {i // CHUNK_SIZE + 1}/{total_chunks}...")

            is_ok, msg = self._run_cmd(base_cmd + chunk)

            if not is_ok:
                failed_chunks += 1
                last_error = msg
                logging.warning(f"Formatting batch failed: {msg}")

        if failed_chunks == 0:
            return {"summary": "Formatting complete."}
        else:
            return {
                "summary": f"Formatting completed with errors in {failed_chunks} batches.\nLast error: {last_error}"
            }
