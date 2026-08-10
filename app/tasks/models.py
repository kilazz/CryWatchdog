from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections import Counter


@dataclass(slots=True, frozen=True)
class AnalyzerResult:
    total_files: int
    duration: float
    extensions_counter: Counter[str]
    error: str | None = None


@dataclass(slots=True, frozen=True)
class CleanerResult:
    summary: str
    failed_files: list[str] = field(default_factory=list)
    modified_count: int = 0
    unchanged_count: int = 0
    error_count: int = 0


@dataclass(slots=True, frozen=True)
class ConverterResult:
    summary: str
    renamed_count: int = 0
    error_count: int = 0


@dataclass(slots=True, frozen=True)
class DuplicateFinderResult:
    summary: str
    duplicates: list[str] = field(default_factory=list)
    removed_dirs: int = 0
    bytes_saved: int = 0


@dataclass(slots=True, frozen=True)
class UnusedAssetResult:
    summary: str
    unused_files: list[str] = field(default_factory=list)
    total_assets: int = 0
    duration: float = 0.0


@dataclass(slots=True, frozen=True)
class MissingAssetResult:
    summary: str
    missing_map: dict[str, list[str]] = field(default_factory=dict)
    total_scanned: int = 0
    duration: float = 0.0


@dataclass(slots=True, frozen=True)
class LuaFormattingResult:
    summary: str
    failed_chunks: int = 0
    last_error: str = ""


@dataclass(slots=True, frozen=True)
class PackerResult:
    summary: str
    packed_count: int = 0


@dataclass(slots=True, frozen=True)
class UnpackerResult:
    summary: str
    unpacked_count: int = 0


@dataclass(slots=True, frozen=True)
class TextureValidatorResult:
    summary: str
    outdated: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    duration: float = 0.0


@dataclass(slots=True, frozen=True)
class TimeOfDayResult:
    summary: str
    created_files: list[str] = field(default_factory=list)
    error: str | None = None
