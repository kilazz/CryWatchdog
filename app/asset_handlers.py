# app/asset_handlers.py
import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path

import chardet
from lxml import etree as ET

from app.config import AppConfig
from app.utils import atomic_write


class AssetHandler(ABC):
    """Abstract base class for asset file parsers and rewriters."""

    @staticmethod
    @abstractmethod
    def parse(file_path: Path) -> set[str]:
        """Parses a file and extracts all referenced asset paths."""
        pass

    @staticmethod
    @abstractmethod
    def rewrite(file_path: Path, replacements: dict[str, str], is_dir_move: bool):
        """Rewrites asset paths in a file based on a replacement mapping."""
        pass


class XmlAssetHandler(AssetHandler):
    """Handles parsing and rewriting of XML-based asset files (e.g., .mtl, .xml)."""

    _EXT_PATTERN = "|".join(re.escape(ext) for ext in AppConfig.TRACKED_ASSET_EXTENSIONS)
    _REGEX_CACHE = re.compile(
        r'(?:File|Texture|filename|path|Material)\s*=\s*["\']([^"\']+(' + _EXT_PATTERN + r'))["\']',
        re.IGNORECASE,
    )

    @staticmethod
    def _get_clean_xml_root_from_content(raw_content: bytes) -> ET.Element | None:
        """Safely parses byte content into an lxml Element, recovering from errors."""
        try:
            if not raw_content or (xml_start_index := raw_content.find(b"<")) == -1:
                return None
            clean_content = raw_content[xml_start_index:]
            parser = ET.XMLParser(recover=True, encoding="utf-8")
            return ET.fromstring(clean_content, parser)
        except Exception:
            try:
                encoding = chardet.detect(clean_content)["encoding"] or "latin-1"
                parser = ET.XMLParser(recover=True, encoding=encoding)
                return ET.fromstring(clean_content, parser)
            except Exception:
                return None

    @staticmethod
    def _get_clean_xml_root(file_path: Path) -> ET.Element | None:
        """Reads a file and returns a clean lxml Element."""
        try:
            return XmlAssetHandler._get_clean_xml_root_from_content(file_path.read_bytes())
        except Exception:
            return None

    @staticmethod
    def parse(file_path: Path) -> set[str]:
        """Parses an XML file using lxml and regex, returning found asset paths."""
        found_paths = set()
        try:
            raw_content = file_path.read_bytes()
            if not raw_content:
                return set()
        except OSError as e:
            logging.warning(f"Could not read file {file_path}: {e}")
            return set()

        if (root := XmlAssetHandler._get_clean_xml_root_from_content(raw_content)) is not None:
            for elem in root.iter():
                for _, value in elem.attrib.items():
                    if isinstance(value, str) and value.strip().lower().endswith(AppConfig.TRACKED_ASSET_EXTENSIONS):
                        found_paths.add(value.strip().replace(os.path.sep, "/"))

        try:
            content = raw_content.decode("utf-8", errors="ignore")
            for match in XmlAssetHandler._REGEX_CACHE.finditer(content):
                found_paths.add(match.group(1).strip().replace(os.path.sep, "/"))
        except Exception as e:
            logging.error(f"Regex parsing failed for {file_path.name}: {e}")

        return {p.lower() for p in found_paths}

    @staticmethod
    def rewrite(file_path: Path, replacements: dict[str, str], is_dir_move: bool):
        """Rewrites asset paths in an XML file using lxml for precision."""
        try:
            root = XmlAssetHandler._get_clean_xml_root(file_path)
            if root is None:
                return
            tree, changed = ET.ElementTree(root), False
            replacements_lower = {k.lower(): v for k, v in replacements.items()}

            for element in root.iter():
                for attr_name, attr_value in list(element.attrib.items()):
                    val_norm = str(attr_value).strip().replace(os.path.sep, "/")
                    val_lower = val_norm.lower()
                    new_val = None

                    if is_dir_move:
                        old_dir, new_dir = next(iter(replacements.items()))
                        if val_lower.startswith(old_dir.lower() + "/"):
                            new_val = new_dir + val_norm[len(old_dir) :]
                    elif val_lower in replacements_lower:
                        new_val = replacements_lower[val_lower]

                    if new_val is not None:
                        element.set(attr_name, new_val)
                        changed = True

            if changed:
                atomic_write(file_path, tree, encoding="utf-8", xml_declaration=False, pretty_print=True)
                logging.info(f"  - [OK] Patched XML '{file_path.name}'")
        except Exception as e:
            logging.error(f"  - [FAIL] Failed to rewrite XML '{file_path.name}': {e}")


class LuaAssetHandler(AssetHandler):
    """Handles parsing and rewriting of Lua script files."""

    _EXT_PATTERN = "|".join(re.escape(ext.lstrip(".")) for ext in AppConfig.TRACKED_ASSET_EXTENSIONS)
    _REGEX_CACHE = re.compile(r"""(['"])([^'"]+\.(?:""" + _EXT_PATTERN + r"""))\1""", re.IGNORECASE)

    @staticmethod
    def parse(file_path: Path) -> set[str]:
        """Parses a Lua file with regex to find string literals that are asset paths."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            return {
                m.group(2).strip().replace(os.path.sep, "/").lower()
                for m in LuaAssetHandler._REGEX_CACHE.finditer(content)
            }
        except Exception as e:
            logging.error(f"Failed to parse LUA file {file_path.name}: {e}")
            return set()

    @staticmethod
    def rewrite(file_path: Path, replacements: dict[str, str], is_dir_move: bool):
        """Rewrites asset paths in a Lua file using regex substitution."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            new_content = content
            if is_dir_move:
                old_dir, new_dir = next(iter(replacements.items()))
                pattern = re.compile(f"(['\"]){re.escape(old_dir)}/([^'\"]*)(['\"])", re.IGNORECASE)
                new_content = pattern.sub(f"\\g<1>{new_dir}/\\g<2>\\g<3>", content)
            else:
                replacements_lower = {old.lower(): new for old, new in replacements.items()}

                def replacer(match: re.Match) -> str:
                    quote, path = match.group(1), match.group(2)
                    new_path = replacements_lower.get(path.lower(), path)
                    return f"{quote}{new_path}{quote}"

                new_content = LuaAssetHandler._REGEX_CACHE.sub(replacer, content)

            if content != new_content:
                atomic_write(file_path, new_content, encoding="utf-8")
                logging.info(f"  - [OK] Patched LUA '{file_path.name}'")
        except Exception as e:
            logging.error(f"  - [FAIL] Failed to rewrite LUA '{file_path.name}': {e}")


# Mapping of file extensions to their handler classes
ASSET_HANDLERS = {
    ".mtl": XmlAssetHandler,
    ".xml": XmlAssetHandler,
    ".lay": XmlAssetHandler,
    ".lyr": XmlAssetHandler,
    ".cdf": XmlAssetHandler,
    ".lua": LuaAssetHandler,
}
