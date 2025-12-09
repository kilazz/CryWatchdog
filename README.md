# CryWatchdog
**CryWatchdog** utility designed for technical art pipelines, specifically tailored to maintain the integrity of **CryEngine** game projects.

It combines real-time asset tracking with a suite of powerful diagnostic and batch-processing tools.

### 👁️ Real-time Reference Patcher (Watchdog)
*   **Live Monitoring:** Automatically detects when files (textures, models, scripts) are renamed or moved within the project directory.
*   **Instant Updates:** Immediately patches references inside `.mtl`, `.xml`, `.lua`, and other container files to match the new file paths.
*   **Format Preservation:** Uses smart Regex replacement to preserve original indentation, comments, and custom formatting (avoids destructive XML parsing).
*   **Smart Folder Handling:** Intelligent handling of directory renames, updating all affected child assets recursively.

### 🩺 Project Health & Diagnostics
*   **Texture Validator:** Scans the project to identify **outdated textures** (where the source `.tif` is newer than the compiled `.dds`) and **missing compiled files**.
*   **Missing Asset Finder:** Scans materials and scripts to identify "broken" references pointing to non-existent textures or models. Includes fuzzy matching logic.
*   **Unused Asset Scavenger:** Identifies "orphaned" files that exist on disk but are not referenced by any level, material, or script, aiding in repository cleanup.
*   **Lua Toolkit:** Provides parallel syntax validation (via `luac`) and auto-formatting (via `StyLua`) for Lua scripts.

### 🚀 Utilities & Converters
*   **TimeOfDay Converter:** Migrates CryEngine 3 TimeOfDay XML files to modern CryEngine 5 Environment Presets (`.env`), preserving curve data.
*   **Deep Duplicate Finder:** Scans for bit-exact duplicates (content + filename match) between a Source and Reference folder to safely clean up redundant backups.
*   **Asset Packer:** Bundles multiple text-based assets into a single archive for easier sharing or storage, with a corresponding unpacker.

### 🧹 Normalization Tools
*   **Batch Lowercase Conversion:** Enforces naming conventions by recursively converting filenames and folders to lowercase.
*   **Standardization:** Normalizes text encoding (UTF-8), line endings (CRLF/LF), and path separators (forward slashes), and strips BOM headers.

## 🛠️ Tech Stack
*   **Python 3.13**
*   **PySide6 (Qt)** for the modern GUI.
*   **Watchdog** library for filesystem events.