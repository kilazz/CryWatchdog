# CryWatchdog
**CryWatchdog** is a utility designed for technical art pipelines to maintain the integrity of **CryEngine** game projects.

It combines real-time asset tracking with a suite of powerful diagnostic and batch-processing tools.

### 👁️ Real-time Reference Patcher
*   **Live Monitoring:** Automatically detects when files (textures, models, scripts) are renamed or moved.
*   **Instant Updates:** Patches references inside `.mtl`, `.xml`, `.lua`, and other container files to match new paths.
*   **Format Preservation:** Uses smart Regex to preserve original indentation and custom formatting.
*   **Smart Folder Handling:** Intelligently handles directory renames, updating all affected child assets.

### 🩺 Project Health & Diagnostics
*   **Texture Validator:** Identifies outdated textures and missing compiled files.
*   **Missing Asset Finder:** Scans materials and scripts for broken references.
*   **Unused Asset Scavenger:** Identifies orphaned files that are not referenced anywhere.
*   **Lua Toolkit:** Provides parallel syntax validation and auto-formatting for Lua scripts.

### 🚀 Utilities & Converters
*   **TimeOfDay Converter:** Migrates CryEngine 3 TimeOfDay XML files to modern CryEngine 5 Environment Presets (`.env`).
*   **Deep Duplicate Finder:** Scans for bit-exact duplicates between folders to safely clean up backups.
*   **Asset Packer:** Bundles multiple text-based assets into a single archive.

### 🧹 Normalization Tools
*   **Batch Lowercase Conversion:** Enforces naming conventions by converting filenames/folders to lowercase.
*   **Standardization:** Normalizes text encoding (UTF-8), line endings, and path separators.

## 🛠️ Tech Stack
*   **Python 3.13**
*   **PySide6 (Qt)**
*   **watchfiles** for fast filesystem events.
