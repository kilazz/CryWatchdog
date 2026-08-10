from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from qfluentwidgets import InfoBar, InfoBarPosition

from app.tasks.analyzer import ProjectAnalyzer
from app.tasks.cleaner import ProjectCleaner
from app.tasks.converter import ProjectConverter
from app.tasks.duplicates import DuplicateFinder
from app.tasks.finding import MissingAssetFinder, UnusedAssetFinder
from app.tasks.models import (
    AnalyzerResult,
    CleanerResult,
    ConverterResult,
    DuplicateFinderResult,
    MissingAssetResult,
    TextureValidatorResult,
    UnusedAssetResult,
)
from app.tasks.texture_validator import TextureValidator
from app.tasks.tod import TimeOfDayConverter
from app.ui.dialogs.cleaner_dlg import CleanerDialog
from app.ui.dialogs.duplicates_dlg import DuplicateFinderDialog
from app.ui.dialogs.finding_dlg import MissingAssetsDialog, UnusedAssetsDialog
from app.ui.dialogs.lua_dlg import LuaToolkitDialog
from app.ui.dialogs.packer_dlg import PackerDialog
from app.ui.dialogs.reports_dlg import AnalysisReportDialog
from app.ui.dialogs.texture_dlg import TextureReportDialog
from app.ui.dialogs.tod_dlg import TimeOfDayDialog

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


class ProjectController:
    def __init__(self, window: MainWindow):
        self.window = window

    def _progress_cb(self, current: int, total: int):
        self.window.core_signals.progressUpdated.emit(current, total)

    def clean_assets(self):
        if not self.window.can_run_task(require_project=True) or self.window.project_root is None:
            return
        project_root = self.window.project_root
        dlg = CleanerDialog(self.window)
        if dlg.exec():
            opts = dlg.get_options()
            self.window.run_task(
                lambda: ProjectCleaner(project_root, progress_callback=self._progress_cb).run(**opts),
                self._on_clean_done,
            )

    def _on_clean_done(self, res: CleanerResult):
        if res.failed_files:
            InfoBar.error(
                title="Cleanup Completed with Errors",
                content=f"Modified: {res.modified_count}, Errors: {res.error_count}",
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window,
            )
        else:
            InfoBar.success(
                title="Cleanup Success",
                content=f"Modified {res.modified_count} files.",
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window,
            )

    def convert_lowercase(self):
        if not self.window.can_run_task(require_project=True) or self.window.project_root is None:
            return
        project_root = self.window.project_root
        dlg = CleanerDialog(self.window)
        if dlg.exec():
            self.window.run_task(
                lambda: ProjectConverter(project_root, progress_callback=self._progress_cb).run(),
                self._on_convert_done,
            )

    def _on_convert_done(self, res: ConverterResult):
        InfoBar.success(
            title="Lowercase Conversion",
            content=res.summary,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window,
        )

    def find_duplicates(self):
        if not self.window.can_run_task(require_project=False):
            return
        dlg = DuplicateFinderDialog(self.window)
        if self.window.project_root:
            dlg.target_selector.set_path(self.window.project_root)

        if dlg.exec():
            ref, tgt = dlg.get_paths()
            if ref and tgt:
                self.window.run_task(
                    lambda: DuplicateFinder(progress_callback=self._progress_cb).run(ref, tgt),
                    self._on_dupes_done,
                )

    def _on_dupes_done(self, res: DuplicateFinderResult):
        InfoBar.info(
            title="Duplicate Scan",
            content=res.summary,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window,
        )

    def convert_tod(self):
        if not self.window.can_run_task(require_project=False):
            return
        dlg = TimeOfDayDialog(self.window)
        if dlg.exec():
            f = dlg.get_file()
            if f:
                self.window.run_task(
                    lambda: TimeOfDayConverter().run(f),
                    lambda r: InfoBar.success("TOD Converter", r.summary, parent=self.window),
                )

    def analyze_project(self):
        if not self.window.can_run_task(require_project=True) or self.window.project_root is None:
            return
        project_root = self.window.project_root
        self.window.run_task(lambda: ProjectAnalyzer(project_root).run(), self._on_analyze_done)

    def _on_analyze_done(self, res: AnalyzerResult):
        prep = defaultdict(dict)
        logger.info("--- [ANALYSIS] Project File Distribution Report ---")
        sorted_extensions = sorted(res.extensions_counter.items(), key=lambda x: x[1], reverse=True)

        for ext, count in sorted_extensions:
            cat = next((c for c, e in AnalysisReportDialog.EXT_CATEGORIES.items() if ext in e), "Other")
            prep[cat][ext] = count

        dlg = AnalysisReportDialog(
            self.window,
            f"Total Files Scanned: {res.total_files} (Time: {res.duration:.2f}s)",
            prep,
        )
        dlg.exec()

    def validate_textures(self):
        if not self.window.can_run_task(require_project=True) or self.window.project_root is None:
            return
        project_root = self.window.project_root
        self.window.run_task(
            lambda: TextureValidator(project_root, progress_callback=self._progress_cb).run(),
            lambda r: TextureReportDialog(self.window, r).exec() if isinstance(r, TextureValidatorResult) else None,
        )

    def find_unused(self):
        if not self.window.can_run_task(require_project=True) or self.window.project_root is None:
            return
        project_root = self.window.project_root
        self.window.run_task(
            lambda: UnusedAssetFinder(project_root, progress_callback=self._progress_cb).run(),
            lambda r: UnusedAssetsDialog(self.window, r).exec() if isinstance(r, UnusedAssetResult) else None,
        )

    def find_missing(self):
        if not self.window.can_run_task(require_project=True) or self.window.project_root is None:
            return
        project_root = self.window.project_root
        self.window.run_task(
            lambda: MissingAssetFinder(project_root, progress_callback=self._progress_cb).run(),
            lambda r: MissingAssetsDialog(self.window, r).exec() if isinstance(r, MissingAssetResult) else None,
        )

    def open_packer(self):
        if not self.window.can_run_task(require_project=False):
            return
        PackerDialog(self.window).exec()

    def open_lua_toolkit(self):
        if not self.window.can_run_task(require_project=True):
            return
        LuaToolkitDialog(self.window).exec()
