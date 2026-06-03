# -*- coding: utf-8 -*-
# Copyright (C) 2026 Sarah Hauser, Karlsruhe Institute of Technology (KIT)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
from pathlib import Path

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterString,
)

from ._utils import resolve_output_folder, write_html, write_json, make_advanced


class BatchRecipeAlgorithm(QgsProcessingAlgorithm):
    RECIPE_JSON = "RECIPE_JSON"
    NOTES = "NOTES"
    DRY_RUN = "DRY_RUN"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    OUT_FOLDER = "OUT_FOLDER"
    REPORT_JSON = "REPORT_JSON"
    REPORT_HTML = "REPORT_HTML"

    def name(self):
        return "batch_recipe"

    def displayName(self):
        return "Expert: batch recipe runner / pipeline placeholder"

    def group(self):
        return "9 Expert / batch"

    def groupId(self):
        return "09_expert"

    def shortHelpString(self):
        return (
            "Optional expert convenience tool. HELIX is designed as standalone modules; this runner stores/validates a recipe for batch execution. "
            "Use the individual modules for normal work."
        )

    def createInstance(self):
        return BatchRecipeAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(self.RECIPE_JSON, "Optional recipe JSON", behavior=QgsProcessingParameterFile.File, extension="json", optional=True))
        self.addParameter(QgsProcessingParameterString(self.NOTES, "Recipe notes / description", defaultValue="", optional=True, multiLine=True))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.DRY_RUN, "dry run only", defaultValue=True)))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT_FOLDER, "Output folder"))
        self.addOutput(QgsProcessingOutputFolder(self.OUT_FOLDER, "Output folder"))
        self.addOutput(QgsProcessingOutputFile(self.REPORT_JSON, "Recipe report JSON"))
        self.addOutput(QgsProcessingOutputFile(self.REPORT_HTML, "Recipe report HTML"))

    def processAlgorithm(self, parameters, context, feedback):
        out_dir = resolve_output_folder(self, parameters, self.OUTPUT_FOLDER, context, "helix_recipe")
        recipe_path = self.parameterAsFile(parameters, self.RECIPE_JSON, context)
        notes = self.parameterAsString(parameters, self.NOTES, context) or ""
        dry = self.parameterAsBool(parameters, self.DRY_RUN, context)
        recipe = {}
        if recipe_path:
            try:
                with open(recipe_path, encoding="utf-8") as f:
                    recipe = json.load(f)
            except Exception as e:
                recipe = {"error": f"Could not read recipe: {e}"}
        report = {"module": "batch_recipe", "status": "dry_run" if dry else "not_executed", "message": "The final HELIX UI is modular. Use this tool only to document or validate a planned batch recipe.", "notes": notes, "recipe": recipe}
        json_path = os.path.join(out_dir, "helix_batch_recipe_report.json")
        html_path = os.path.join(out_dir, "helix_batch_recipe_report.html")
        write_json(json_path, report)
        write_html(html_path, "HELIX Batch Recipe", [("Status", f"<pre>{report}</pre>")])
        return {self.OUT_FOLDER: out_dir, self.REPORT_JSON: json_path, self.REPORT_HTML: html_path}
