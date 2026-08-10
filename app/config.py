import json
import logging
import sys
from collections import namedtuple
from enum import Enum, auto
from pathlib import Path
from typing import ClassVar

from PySide6.QtGui import QFont

logger = logging.getLogger(__name__)


class AppConfig:
    """Encapsulates all core application configurations and constants."""

    PROJECT_ROOT = (
        Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    )
    TOOLS_DIR = PROJECT_ROOT / "bin"
    CONFIG_FILE = Path("config.json")

    LUA_COMPILER_PATH = TOOLS_DIR / "luac55.exe"
    STYLUA_PATH = TOOLS_DIR / "stylua.exe"

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

    TEXTURE_EXTENSIONS: ClassVar[set[str]] = set(DEFAULT_TEXTURE_EXTS)
    TRACKED_ASSET_EXTENSIONS: ClassVar[list[str]] = list(DEFAULT_TRACKED_EXTS)

    HANDLED_TEXT_EXTENSIONS: ClassVar[set[str]] = {".mtl", ".xml", ".lay", ".lyr", ".cdf", ".lua"}
    XML_EXTENSIONS: ClassVar[set[str]] = {".mtl", ".xml", ".lay", ".lyr", ".cdf"}

    @classmethod
    def load(cls):
        if not cls.CONFIG_FILE.exists():
            return

        try:
            with open(cls.CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)

                if "textures" in data:
                    cls.TEXTURE_EXTENSIONS = set(data["textures"])

                if "tracked" in data:
                    cls.TRACKED_ASSET_EXTENSIONS = list(data["tracked"])

            logger.info(f"Configuration loaded from {cls.CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Failed to load config.json, using defaults. Error: {e}")

    @classmethod
    def save(cls):
        data = {
            "textures": sorted(cls.TEXTURE_EXTENSIONS),
            "tracked": cls.TRACKED_ASSET_EXTENSIONS,
        }
        try:
            with open(cls.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            logger.info(f"Configuration saved to {cls.CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Failed to save config.json: {e}")


AppConfig.load()


class UIConfig:
    FONT_MONOSPACE = QFont("Consolas", 10)
    COLOR_SUCCESS = "#66BB6A"
    COLOR_ERROR = "#E57373"
    COLOR_WARNING = "#FFCC80"
    COLOR_INFO = "#42A5F5"
    COLOR_IDLE = "white"
    COLOR_DRY_RUN = "#CE93D8"


class AppState(Enum):
    IDLE = auto()
    INDEXING = auto()
    WATCHING = auto()
    STOPPING = auto()
    TASK_RUNNING = auto()


class CleanupStatus(Enum):
    MODIFIED = auto()
    UNCHANGED = auto()
    SKIPPED = auto()
    ERROR = auto()


LuaFileAnalysisResult = namedtuple(
    "LuaFileAnalysisResult",
    ["relative_path", "is_syntax_ok", "message", "encoding", "status"],
)
