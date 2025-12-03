# app/asset_handlers.py
import logging
import mmap
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import AppConfig
from app.utils import atomic_write


class AssetHandler(ABC):
    """
    Abstract Base Class for handling different file formats (XML, Lua, etc.).
    Defines methods for parsing dependencies and rewriting paths.
    """

    @staticmethod
    @abstractmethod
    def parse(file_path: Path) -> set[str]:
        """
        Scans the file for referenced assets.
        Returns a set of normalized, lower-case relative paths.
        """
        pass

    @staticmethod
    @abstractmethod
    def rewrite(file_path: Path, replacements: dict[str, str], is_dir_move: bool):
        """
        Replaces paths in the file based on the provided dictionary.
        Uses atomic writing to prevent data corruption.
        """
        pass


class XmlAssetHandler(AssetHandler):
    """
    Optimized handler using MMAP for reading and REGEX for writing.
    Preserves original formatting/indentation perfectly by avoiding XML parsers.

    Updated to strictly enforce quote pairing (e.g. File="Path").
    """

    # Patterns for XML/MTL attributes commonly used in CryEngine/Lumberyard
    _EXT_PATTERN = "|".join(re.escape(ext) for ext in AppConfig.TRACKED_ASSET_EXTENSIONS)

    # Regex for finding paths in bytes (for mmap)
    # Group 1: Opening Quote
    # Group 2: The Path
    # \1: Backreference to ensure closing quote matches opening quote
    _BYTES_REGEX = re.compile(
        rb'(?:File|Texture|filename|path|Material)\s*=\s*([\'"])([^"\']+(?:' + _EXT_PATTERN.encode("utf-8") + rb"))\1",
        re.IGNORECASE,
    )

    @staticmethod
    def parse(file_path: Path) -> set[str]:
        """Parses file using memory mapping (zero-copy reading)."""
        found_paths = set()

        if file_path.stat().st_size == 0:
            return set()

        # We intentionally do NOT catch OSError here.
        # If the file is locked/busy, let the error bubble up so the
        # caller (watcher.py) can catch it and retry the operation.
        with (
            open(file_path, "rb") as f,
            mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm,
        ):
            for match in XmlAssetHandler._BYTES_REGEX.finditer(mm):
                try:
                    # Group 2 is the path (Group 1 is the quote)
                    path_str = match.group(2).decode("utf-8", errors="ignore")
                    found_paths.add(path_str.strip().replace(os.path.sep, "/"))
                except Exception:
                    continue

        return {p.lower() for p in found_paths}

    @staticmethod
    def rewrite(file_path: Path, replacements: dict[str, str], is_dir_move: bool):
        """
        Rewrites using regex substitution on text content.
        This preserves custom formatting, comments, and structure better than XML parsers.
        """
        try:
            # Read as text for replacement
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            original_content = content

            replacements_lower = {k.lower(): v for k, v in replacements.items()}

            def replace_callback(match):
                # Group 1: Key + whitespace + equals + whitespace (e.g. 'File = ')
                # Group 2: Opening Quote (e.g. '"')
                # Group 3: Path content
                prefix, quote, old_path = match.groups()

                old_path_norm = old_path.strip().replace(os.path.sep, "/")
                old_path_lower = old_path_norm.lower()

                new_val = None

                if is_dir_move:
                    old_dir, new_dir = next(iter(replacements.items()))
                    if old_path_lower.startswith(old_dir.lower() + "/"):
                        # Slice and dice path
                        remainder = old_path_norm[len(old_dir) :]
                        new_val = f"{new_dir}{remainder}"
                elif old_path_lower in replacements_lower:
                    new_val = replacements_lower[old_path_lower]

                if new_val:
                    # Reconstruct using the captured quote to match style
                    return f"{prefix}{quote}{new_val}{quote}"

                return match.group(0)

            # Construct Regex Dynamically
            # Matches: Key = "Value" OR Key='Value'
            # \2 refers back to the capturing group of the opening quote
            pattern_str = (
                r"((?:File|Texture|filename|path|Material)\s*=\s*)"  # Group 1: Key
                r'(["\'])'  # Group 2: Quote
                r'([^"\']+(?:' + XmlAssetHandler._EXT_PATTERN + r"))"  # Group 3: Path
                r"\2"  # Backref to Group 2
            )
            pattern = re.compile(pattern_str, re.IGNORECASE)

            new_content = pattern.sub(replace_callback, content)

            if new_content != original_content:
                atomic_write(file_path, new_content, encoding="utf-8")
                logging.info(f"  - [OK] Patched '{file_path.name}' (Format Preserved)")

        except Exception as e:
            logging.error(f"  - [FAIL] Failed to rewrite '{file_path.name}': {e}")


class LuaAssetHandler(AssetHandler):
    """
    Handler for Lua scripts.
    Matches strings that end with tracked extensions (e.g., "path/to/texture.dds").
    """

    _EXT_PATTERN = "|".join(re.escape(ext.lstrip(".")) for ext in AppConfig.TRACKED_ASSET_EXTENSIONS)

    # Bytes regex for mmap
    # Group 1: Quote
    # Group 2: Path
    # \1: Backreference to quote
    _BYTES_REGEX = re.compile(
        rb'([\'"])([^\'"]+\.(?:' + _EXT_PATTERN.encode("utf-8") + rb"))\1",
        re.IGNORECASE,
    )

    # Text regex for rewrite
    _TEXT_REGEX = re.compile(r'([\'"])([^\'"]+\.(?:' + _EXT_PATTERN + r"))\1", re.IGNORECASE)

    @staticmethod
    def parse(file_path: Path) -> set[str]:
        if file_path.stat().st_size == 0:
            return set()
        found = set()

        # Let OSError bubble up for retry logic in watcher
        with (
            open(file_path, "rb") as f,
            mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm,
        ):
            for m in LuaAssetHandler._BYTES_REGEX.finditer(mm):
                path_str = m.group(2).decode("utf-8", errors="ignore")
                found.add(path_str.strip().replace(os.path.sep, "/").lower())
        return found

    @staticmethod
    def rewrite(file_path: Path, replacements: dict[str, str], is_dir_move: bool):
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")

            replacements_lower = {k.lower(): v for k, v in replacements.items()}

            def replacer(match: re.Match) -> str:
                quote, path = match.group(1), match.group(2)
                path_norm = path.replace(os.path.sep, "/")
                path_lower = path_norm.lower()

                new_path = None
                if is_dir_move:
                    old_dir, new_dir = next(iter(replacements.items()))
                    if path_lower.startswith(old_dir.lower() + "/"):
                        new_path = f"{new_dir}{path_norm[len(old_dir) :]}"
                else:
                    new_path = replacements_lower.get(path_lower)

                if new_path:
                    return f"{quote}{new_path}{quote}"
                return match.group(0)

            new_content = LuaAssetHandler._TEXT_REGEX.sub(replacer, content)

            if content != new_content:
                atomic_write(file_path, new_content, encoding="utf-8")
                logging.info(f"  - [OK] Patched LUA '{file_path.name}'")
        except Exception as e:
            logging.error(f"  - [FAIL] Failed to rewrite LUA '{file_path.name}': {e}")


ASSET_HANDLERS = {
    ".mtl": XmlAssetHandler,
    ".xml": XmlAssetHandler,
    ".lay": XmlAssetHandler,
    ".lyr": XmlAssetHandler,
    ".cdf": XmlAssetHandler,
    ".lua": LuaAssetHandler,
}
