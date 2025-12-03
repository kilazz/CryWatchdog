# app/config.py
import json
import logging
import re
from collections import namedtuple
from enum import Enum, auto
from pathlib import Path
from typing import ClassVar

from PySide6.QtGui import QFont


class AppConfig:
    """
    Encapsulates all core application configurations and constants.
    Loads settings from 'config.json' if available, otherwise uses defaults.
    """

    # Path to the external configuration file
    CONFIG_FILE = Path("config.json")

    # --- Default Constants (Fallback) ---
    # RUF012: Annotated with ClassVar because they are mutable class attributes
    DEFAULT_TEXTURE_EXTS: ClassVar[set[str]] = {
        ".dds",
        ".tif",
        ".tiff",
        ".png",
        ".jpg",
        ".jpeg",
        ".tga",
        ".bmp",
        ".gif",
        ".hdr",
        ".exr",
        ".gfx",
    }

    DEFAULT_TRACKED_EXTS: ClassVar[list[str]] = [
        ".dds",
        ".tif",
        ".png",
        ".jpg",
        ".jpeg",
        ".tga",
        ".bmp",
        ".gif",
        ".hdr",
        ".mtl",
        ".xml",
        ".lay",
        ".lyr",
        ".cdf",
        ".lua",
        ".cgf",
        ".chr",
        ".cga",
        ".skin",
        ".adb",
    ]

    # --- Mutable Runtime Configurations ---
    # These are loaded from JSON or initialized with defaults.
    TEXTURE_EXTENSIONS: ClassVar[set[str]] = set(DEFAULT_TEXTURE_EXTS)
    # FIX: Changed list[str] to ClassVar[list[str]]
    TRACKED_ASSET_EXTENSIONS: ClassVar[list[str]] = list(DEFAULT_TRACKED_EXTS)

    # --- Static / Hardcoded Configurations ---
    HANDLED_TEXT_EXTENSIONS: ClassVar[set[str]] = {".mtl", ".xml", ".lay", ".lyr", ".cdf", ".lua"}
    XML_EXTENSIONS: ClassVar[set[str]] = {".mtl", ".xml", ".lay", ".lyr", ".cdf"}

    LOG_MAX_BLOCK_COUNT: int = 5000
    LUA_COMPILER_EXE_NAME: str = "luac54.exe"
    STYLUO_EXE_NAME: str = "stylua.exe"
    INVALID_PATH_CHARS_RE = re.compile(r"[<>|?*]")
    MAX_CMD_LINE_LENGTH = 8191

    @classmethod
    def load(cls):
        """
        Attempts to load configuration from config.json.
        Updates TEXTURE_EXTENSIONS and TRACKED_ASSET_EXTENSIONS if successful.
        """
        if not cls.CONFIG_FILE.exists():
            return

        try:
            with open(cls.CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)

                # Update Textures (convert list to set for O(1) lookups)
                if "textures" in data:
                    cls.TEXTURE_EXTENSIONS = set(data["textures"])

                # Update Tracked Assets
                if "tracked" in data:
                    cls.TRACKED_ASSET_EXTENSIONS = list(data["tracked"])

            logging.info(f"Configuration loaded from {cls.CONFIG_FILE}")
        except Exception as e:
            logging.error(f"Failed to load config.json, using defaults. Error: {e}")

    @classmethod
    def save(cls):
        """
        Saves the current configuration to config.json.
        """
        data = {"textures": sorted(list(cls.TEXTURE_EXTENSIONS)), "tracked": cls.TRACKED_ASSET_EXTENSIONS}
        try:
            with open(cls.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            logging.info(f"Configuration saved to {cls.CONFIG_FILE}")
        except Exception as e:
            logging.error(f"Failed to save config.json: {e}")


# Automatically load config when module is imported
AppConfig.load()


class UIConfig:
    """Encapsulates UI-specific constants like colors, fonts, and text."""

    FONT_MONOSPACE = QFont("Consolas", 10)
    COLOR_SUCCESS = "#66BB6A"
    COLOR_ERROR = "#E57373"
    COLOR_WARNING = "#FFCC80"
    COLOR_INFO = "#42A5F5"
    COLOR_IDLE = "white"
    COLOR_DRY_RUN = "#CE93D8"


class AppState(Enum):
    """Defines the possible operational states of the application."""

    IDLE = auto()
    INDEXING = auto()
    WATCHING = auto()
    STOPPING = auto()
    TASK_RUNNING = auto()


class CleanupStatus(Enum):
    """Represents the outcome of a file cleanup operation."""

    MODIFIED = auto()
    UNCHANGED = auto()
    SKIPPED = auto()
    ERROR = auto()


# Custom named tuple for structured Lua analysis results
LuaFileAnalysisResult = namedtuple(
    "LuaFileAnalysisResult",
    ["relative_path", "is_syntax_ok", "message", "encoding", "status"],
)
