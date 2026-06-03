# -*- coding: utf-8 -*-
# Copyright (C) 2026 Sarah Hauser, Karlsruhe Institute of Technology (KIT)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import shutil
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

from ._utils import resolve_output_folder, write_html, write_json, make_advanced, safe_feedback


class ExportReportAlgorithm(QgsProcessingAlgorithm):
    INPUT_FOLDER = "INPUT_FOLDER"
    INCLUDE_PATTERN = "INCLUDE_PATTERN"
    COPY_FILES = "COPY_FILES"
    WRITE_HTML = "WRITE_HTML"
    COMPUTE_RASTER_STATS = "COMPUTE_RASTER_STATS"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    OUT_FOLDER = "OUT_FOLDER"
    MANIFEST_JSON = "MANIFEST_JSON"
    REPORT_HTML = "REPORT_HTML"

    def name(self):
        return "export_report"

    def displayName(self):
        return "Export & report: ML-ready bundle manifest"

    def group(self):
        return "7 Export"

    def groupId(self):
        return "07_export"

    def shortHelpString(self):
        return (
            "Creates a lightweight HELIX export manifest and HTML report from an output folder. Optionally copies matching files into a clean ML-ready bundle. "
            "This is the reproducibility/QA step, not a heavy scientific module."
        )

    def createInstance(self):
        return ExportReportAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(self.INPUT_FOLDER, "Input/output folder to scan", behavior=QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterString(self.INCLUDE_PATTERN, "Filename patterns/extensions to include", defaultValue=".tif,.tiff,.vrt,.csv,.json,.html", optional=True))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.COPY_FILES, "copy matching files into export folder", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_HTML, "write HTML report", defaultValue=True)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.COMPUTE_RASTER_STATS, "compute simple raster statistics", defaultValue=True)))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT_FOLDER, "Export/report folder"))
        self.addOutput(QgsProcessingOutputFolder(self.OUT_FOLDER, "Export/report folder"))
        self.addOutput(QgsProcessingOutputFile(self.MANIFEST_JSON, "Manifest JSON"))
        self.addOutput(QgsProcessingOutputFile(self.REPORT_HTML, "HTML report"))

    def processAlgorithm(self, parameters, context, feedback):
        input_folder = self.parameterAsFile(parameters, self.INPUT_FOLDER, context)
        out_dir = resolve_output_folder(self, parameters, self.OUTPUT_FOLDER, context, "helix_export")
        patterns = [p.strip().lower() for p in (self.parameterAsString(parameters, self.INCLUDE_PATTERN, context) or "").split(",") if p.strip()]
        copy_files = self.parameterAsBool(parameters, self.COPY_FILES, context)
        write_html_flag = self.parameterAsBool(parameters, self.WRITE_HTML, context)
        stats_flag = self.parameterAsBool(parameters, self.COMPUTE_RASTER_STATS, context)

        files = []
        for root, _, names in os.walk(input_folder):
            for name in names:
                low = name.lower()
                if patterns and not any(low.endswith(p) or p in low for p in patterns):
                    continue
                src = os.path.join(root, name)
                rel = os.path.relpath(src, input_folder)
                dest = ""
                if copy_files:
                    dest = os.path.join(out_dir, rel)
                    Path(dest).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                item = {"relative_path": rel, "source_path": src, "export_path": dest, "size_bytes": os.path.getsize(src)}
                if stats_flag and low.endswith((".tif", ".tiff", ".vrt")):
                    try:
                        from osgeo import gdal
                        ds = gdal.Open(src)
                        if ds:
                            item["raster"] = {"width": ds.RasterXSize, "height": ds.RasterYSize, "bands": ds.RasterCount, "projection": ds.GetProjection()[:120]}
                            band_stats = []
                            for bi in range(1, min(ds.RasterCount, 10) + 1):
                                b = ds.GetRasterBand(bi)
                                st = b.GetStatistics(False, True)
                                band_stats.append({"band": bi, "min": st[0], "max": st[1], "mean": st[2], "std": st[3], "nodata": b.GetNoDataValue(), "description": b.GetDescription()})
                            item["band_stats"] = band_stats
                            ds = None
                    except Exception as e:
                        item["stats_error"] = str(e)
                files.append(item)

        manifest = {"module": "export_report", "input_folder": input_folder, "export_folder": out_dir, "copied_files": copy_files, "file_count": len(files), "files": files}
        manifest_path = os.path.join(out_dir, "helix_manifest.json")
        write_json(manifest_path, manifest)
        html_path = os.path.join(out_dir, "helix_report.html")
        if write_html_flag:
            rows = "".join(f"<tr><td>{f['relative_path']}</td><td>{f['size_bytes']}</td><td>{f.get('raster', {}).get('width','')}</td><td>{f.get('raster', {}).get('height','')}</td><td>{f.get('raster', {}).get('bands','')}</td></tr>" for f in files)
            table = f"<table><tr><th>File</th><th>Bytes</th><th>Width</th><th>Height</th><th>Bands</th></tr>{rows}</table>"
            write_html(html_path, "HELIX Export & Report", [("Summary", f"<p>Files: {len(files)}</p><p>Copied: {copy_files}</p>"), ("Files", table)])
        else:
            html_path = ""
        safe_feedback(feedback, f"Wrote manifest: {manifest_path}")
        return {self.OUT_FOLDER: out_dir, self.MANIFEST_JSON: manifest_path, self.REPORT_HTML: html_path}
