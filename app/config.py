# app/config.py
import re
from collections import namedtuple
from enum import Enum, auto

from PySide6.QtGui import QFont


class AppConfig:
    """Encapsulates all core application configurations and constants."""

    TEXTURE_EXTENSIONS: set[str] = {
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
    TRACKED_ASSET_EXTENSIONS: tuple[str, ...] = (
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
    )
    HANDLED_TEXT_EXTENSIONS: set[str] = {".mtl", ".xml", ".lay", ".lyr", ".cdf", ".lua"}
    XML_EXTENSIONS: set[str] = {".mtl", ".xml", ".lay", ".lyr", ".cdf"}
    LOG_MAX_BLOCK_COUNT: int = 5000
    LUA_COMPILER_EXE_NAME: str = "luac54.exe"
    STYLUO_EXE_NAME: str = "stylua.exe"
    INVALID_PATH_CHARS_RE = re.compile(r"[<>|?*]")
    MAX_CMD_LINE_LENGTH = 8191


class UIConfig:
    """Encapsulates UI-specific constants like colors, fonts, and text."""

    FONT_MONOSPACE = QFont("Consolas", 10)
    COLOR_SUCCESS = "#66BB6A"
    COLOR_ERROR = "#E57373"
    COLOR_WARNING = "#FFCC80"
    COLOR_INFO = "#42A5F5"
    COLOR_IDLE = "white"


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
