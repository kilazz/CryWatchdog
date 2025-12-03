# CryWatchdog

**CryWatchdog** is a comprehensive utility designed for technical art pipelines, specifically tailored to maintain the integrity of game projects CryEngine

### 👁️ Real-time Reference Patcher (Watchdog)
*   **Live Monitoring:** Automatically detects when files (textures, models, scripts) are renamed or moved within the project directory.
*   **Instant Updates:** Immediately patches references inside `.mtl`, `.xml`, `.lua`, and other container files to match the new file paths.
*   **Format Preservation:** Uses smart Regex replacement to preserve original indentation, comments, and custom formatting (unlike standard XML parsers).
*   **Smart Folder Handling:** Intelligent handling of directory renames, updating all affected child assets recursively.

### 🩺 Project Health & Diagnostics
*   **Missing Asset Finder:** Scans materials and scripts to identify "broken" references pointing to non-existent textures or models. Includes fuzzy matching (e.g., checking for `.dds` if `.tif` is referenced).
*   **Unused Asset Scavenger:** Identifies "orphaned" files that exist on the disk but are not referenced by any level, material, or script, helping to reduce project size.
*   **Lua Toolkit:** Provides syntax validation, encoding checks, and auto-formatting (via `StyLua`) for Lua scripts.

### 🧹 Normalization Tools
*   **Batch Lowercase Conversion:** Enforces naming conventions by converting filenames and folders to lowercase.
*   **Standardization:** Normalizes text encoding (UTF-8), line endings, and path separators (forward slashes), and removes BOM headers.

## 🛠️ Tech Stack
*   **Python 3.13**
*   **PySide6 (Qt)** for the GUI
*   **Watchdog** for filesystem events
*   **Multithreading** (QThreadPool/ProcessPoolExecutor) for non-blocking UI
