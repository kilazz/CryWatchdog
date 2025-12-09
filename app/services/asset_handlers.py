# app/services/asset_handlers.py
import logging
import mmap
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import AppConfig
from app.core.utils import atomic_write


class AssetHandler(ABC):
    """
    Abstract Base Class for handling different file formats (XML, Lua, etc.).
    Defines methods for parsing dependencies and rewriting paths.
    """

    @staticmethod
    @abstractmethod
    def parse(file_path: Path) -> set[str]:
        pass

    @staticmethod
    @abstractmethod
    def rewrite(file_path: Path, replacements: dict[str, str], is_dir_move: bool):
        pass


class XmlAssetHandler(AssetHandler):
    """
    Optimized handler using MMAP for reading and REGEX for writing.
    Preserves original formatting/indentation perfectly by avoiding XML parsers.
    """

    _EXT_PATTERN = "|".join(re.escape(ext) for ext in AppConfig.TRACKED_ASSET_EXTENSIONS)

    _BYTES_REGEX = re.compile(
        rb'(?:File|Texture|filename|path|Material)\s*=\s*([\'"])([^"\']+(?:' + _EXT_PATTERN.encode("utf-8") + rb"))\1",
        re.IGNORECASE,
    )

    @staticmethod
    def parse(file_path: Path) -> set[str]:
        found_paths = set()
        if file_path.stat().st_size == 0:
            return set()

        with (
            open(file_path, "rb") as f,
            mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm,
        ):
            for match in XmlAssetHandler._BYTES_REGEX.finditer(mm):
                try:
                    path_str = match.group(2).decode("utf-8", errors="ignore")
                    found_paths.add(path_str.strip().replace(os.path.sep, "/"))
                except Exception:
                    continue

        return {p.lower() for p in found_paths}

    @staticmethod
    def rewrite(file_path: Path, replacements: dict[str, str], is_dir_move: bool):
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            original_content = content
            replacements_lower = {k.lower(): v for k, v in replacements.items()}

            def replace_callback(match):
                prefix, quote, old_path = match.groups()
                old_path_norm = old_path.strip().replace(os.path.sep, "/")
                old_path_lower = old_path_norm.lower()
                new_val = None

                if is_dir_move:
                    old_dir, new_dir = next(iter(replacements.items()))
                    if old_path_lower.startswith(old_dir.lower() + "/"):
                        remainder = old_path_norm[len(old_dir) :]
                        new_val = f"{new_dir}{remainder}"
                elif old_path_lower in replacements_lower:
                    new_val = replacements_lower[old_path_lower]

                if new_val:
                    return f"{prefix}{quote}{new_val}{quote}"
                return match.group(0)

            pattern_str = (
                r"((?:File|Texture|filename|path|Material)\s*=\s*)"
                r'(["\'])'
                r'([^"\']+(?:' + XmlAssetHandler._EXT_PATTERN + r"))"
                r"\2"
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
    Matches strings that end with tracked extensions.
    """

    _EXT_PATTERN = "|".join(re.escape(ext.lstrip(".")) for ext in AppConfig.TRACKED_ASSET_EXTENSIONS)
    _BYTES_REGEX = re.compile(
        rb'([\'"])([^\'"]+\.(?:' + _EXT_PATTERN.encode("utf-8") + rb"))\1",
        re.IGNORECASE,
    )
    _TEXT_REGEX = re.compile(r'([\'"])([^\'"]+\.(?:' + _EXT_PATTERN + r"))\1", re.IGNORECASE)

    @staticmethod
    def parse(file_path: Path) -> set[str]:
        if file_path.stat().st_size == 0:
            return set()
        found = set()
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
