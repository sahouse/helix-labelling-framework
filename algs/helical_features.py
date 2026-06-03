# -*- coding: utf-8 -*-
# Copyright (C) 2026 Sarah Hauser, Karlsruhe Institute of Technology (KIT)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import math
import os

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
)

from ._utils import (
    parse_dates_text,
    parse_dates_csv,
    dates_from_folder,
    doy_fraction,
    resolve_output_folder,
    write_csv,
    write_html,
    write_json,
    add_raster_to_project,
    make_advanced,
    load_class_ids,
    read_class_schema,
    band_description,
)


class HelicalFeaturesAlgorithm(QgsProcessingAlgorithm):
    DATES_TEXT = "DATES_TEXT"
    DATES_CSV = "DATES_CSV"
    DATE_FIELD = "DATE_FIELD"
    RASTER_FOLDER = "RASTER_FOLDER"
    REF_GRID = "REF_GRID"
    CLASS_STACK = "CLASS_STACK"
    HARD_LABEL_RASTER = "HARD_LABEL_RASTER"
    CLASS_IDS = "CLASS_IDS"
    CLASS_SCHEMA_CSV = "CLASS_SCHEMA_CSV"
    NODATA = "NODATA"
    FEATURE_MODE = "FEATURE_MODE"
    HARMONICS = "HARMONICS"
    YEAR_LENGTH = "YEAR_LENGTH"
    ORIGIN_DOY = "ORIGIN_DOY"
    INCLUDE_LINEAR = "INCLUDE_LINEAR"
    INCLUDE_DELTA = "INCLUDE_DELTA"
    WRITE_RASTER_STACKS = "WRITE_RASTER_STACKS"
    GRID_STEP_DAYS = "GRID_STEP_DAYS"
    WRITE_CLASS_INTERACTIONS = "WRITE_CLASS_INTERACTIONS"
    LOAD_OUTPUTS = "LOAD_OUTPUTS"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    OUT_FOLDER = "OUT_FOLDER"
    FEATURES_CSV = "FEATURES_CSV"
    REPORT_JSON = "REPORT_JSON"

    MODE_OPTIONS = [
        "HELIX compact annual wave features",
        "Annual + semiannual Fourier waves",
        "Annual + semiannual + quarterly waves",
        "Full multi-harmonic Fourier up to selected K",
    ]

    def name(self):
        return "helical_features"

    def displayName(self):
        return "Helical / wave features from EO dates"

    def group(self):
        return "4 Helical features"

    def groupId(self):
        return "04_helical"

    def shortHelpString(self):
        return (
            "Calculates HELIX helical/wave calendar features from EO dates. The year is represented as cyclic sin/cos coordinates, optionally with multiple harmonics, "
            "linear time index and date-spacing features. Can output a CSV, optional constant raster feature stacks aligned to a reference grid, and optional class × "
            "helical interaction stacks from either a class/soft-target stack or a single-band hard label raster that is one-hot encoded internally."
        )

    def createInstance(self):
        return HelicalFeaturesAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(self.DATES_TEXT, "EO dates as text/list", defaultValue="", optional=True))
        self.addParameter(QgsProcessingParameterFile(self.DATES_CSV, "EO dates CSV", behavior=QgsProcessingParameterFile.File, extension="csv", optional=True))
        self.addParameter(QgsProcessingParameterString(self.DATE_FIELD, "Date field in CSV", defaultValue="date", optional=True))
        self.addParameter(QgsProcessingParameterFile(self.RASTER_FOLDER, "Optional raster folder; dates parsed from filenames", behavior=QgsProcessingParameterFile.Folder, optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(self.REF_GRID, "Optional reference grid for raster feature stacks", optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(self.CLASS_STACK, "Optional class/soft-target stack for class × helical interaction features", optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(self.HARD_LABEL_RASTER, "Optional hard label raster for class × helical interactions", optional=True))
        self.addParameter(make_advanced(QgsProcessingParameterString(self.CLASS_IDS, "Class IDs for hard-label interaction input; empty = infer", defaultValue="", optional=True)))
        self.addParameter(make_advanced(QgsProcessingParameterFile(self.CLASS_SCHEMA_CSV, "Optional class schema CSV", behavior=QgsProcessingParameterFile.File, extension="csv", optional=True)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.NODATA, "NoData/background value for hard label raster", type=QgsProcessingParameterNumber.Integer, defaultValue=0)))
        self.addParameter(make_advanced(QgsProcessingParameterEnum(self.FEATURE_MODE, "feature mode", self.MODE_OPTIONS, defaultValue=1)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.HARMONICS, "maximum harmonic K", type=QgsProcessingParameterNumber.Integer, minValue=1, maxValue=8, defaultValue=2)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.YEAR_LENGTH, "year length used for phase", type=QgsProcessingParameterNumber.Double, minValue=300.0, maxValue=400.0, defaultValue=365.2425)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.ORIGIN_DOY, "phase origin DOY", type=QgsProcessingParameterNumber.Double, minValue=1.0, maxValue=366.0, defaultValue=1.0)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.INCLUDE_LINEAR, "include linear time / year index", defaultValue=True)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.INCLUDE_DELTA, "include date-spacing features", defaultValue=True)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_RASTER_STACKS, "write constant raster feature stack(s)", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.GRID_STEP_DAYS, "fill in-between dates every N days; 0 = off", type=QgsProcessingParameterNumber.Integer, minValue=0, maxValue=366, defaultValue=0)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_CLASS_INTERACTIONS, "write class × helical interaction stacks", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.LOAD_OUTPUTS, "load raster outputs into QGIS", defaultValue=False)))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT_FOLDER, "Output folder"))
        self.addOutput(QgsProcessingOutputFolder(self.OUT_FOLDER, "Output folder"))
        self.addOutput(QgsProcessingOutputFile(self.FEATURES_CSV, "Helical feature CSV"))
        self.addOutput(QgsProcessingOutputFile(self.REPORT_JSON, "Report JSON"))

    def processAlgorithm(self, parameters, context, feedback):
        out_dir = resolve_output_folder(self, parameters, self.OUTPUT_FOLDER, context, "helix_helical")
        date_field = self.parameterAsString(parameters, self.DATE_FIELD, context) or "date"
        dates = []
        dates += parse_dates_text(self.parameterAsString(parameters, self.DATES_TEXT, context) or "")
        dates += parse_dates_csv(self.parameterAsFile(parameters, self.DATES_CSV, context), date_field)
        dates += dates_from_folder(self.parameterAsFile(parameters, self.RASTER_FOLDER, context))
        dates = sorted(dict.fromkeys(dates))
        grid_step_days = self.parameterAsInt(parameters, self.GRID_STEP_DAYS, context)
        if grid_step_days and len(dates) >= 2:
            from datetime import timedelta
            grid_dates = []
            cur = dates[0]
            while cur <= dates[-1]:
                grid_dates.append(cur)
                cur = cur + timedelta(days=int(grid_step_days))
            dates = sorted(dict.fromkeys(dates + grid_dates))
        if not dates:
            raise QgsProcessingException("No dates found. Provide text, CSV, or a raster folder with dates in filenames.")

        mode = self.parameterAsEnum(parameters, self.FEATURE_MODE, context)
        max_k = self.parameterAsInt(parameters, self.HARMONICS, context)
        if mode == 0:
            max_k = 1
        elif mode == 1:
            max_k = max(2, min(max_k, 2))
        elif mode == 2:
            max_k = max(4, min(max_k, 4))
        year_length = self.parameterAsDouble(parameters, self.YEAR_LENGTH, context)
        origin = self.parameterAsDouble(parameters, self.ORIGIN_DOY, context)
        include_linear = self.parameterAsBool(parameters, self.INCLUDE_LINEAR, context)
        include_delta = self.parameterAsBool(parameters, self.INCLUDE_DELTA, context)
        write_rasters = self.parameterAsBool(parameters, self.WRITE_RASTER_STACKS, context)
        write_class_interactions = self.parameterAsBool(parameters, self.WRITE_CLASS_INTERACTIONS, context)
        load_outputs = self.parameterAsBool(parameters, self.LOAD_OUTPUTS, context)

        rows = []
        all_feature_names = []
        for idx, d in enumerate(dates):
            phase = doy_fraction(d, year_length=year_length, origin_doy=origin)
            row = {"index": idx, "date": d.isoformat(), "year": d.year, "doy": d.timetuple().tm_yday, "phase_annual": round(phase, 8)}
            for k in range(1, max_k + 1):
                row[f"sin_k{k}"] = math.sin(2.0 * math.pi * k * phase)
                row[f"cos_k{k}"] = math.cos(2.0 * math.pi * k * phase)
            if include_linear:
                row["t_index"] = idx
                row["year_centered"] = d.year - dates[0].year
            if include_delta:
                row["delta_prev_days"] = "" if idx == 0 else (d - dates[idx - 1]).days
                row["delta_next_days"] = "" if idx == len(dates) - 1 else (dates[idx + 1] - d).days
            rows.append(row)
            all_feature_names = list(row.keys())

        csv_path = os.path.join(out_dir, "helix_helical_features.csv")
        write_csv(csv_path, rows, all_feature_names)
        raster_paths = []
        interaction_paths = []
        ref = self.parameterAsRasterLayer(parameters, self.REF_GRID, context)
        class_stack_layer = self.parameterAsRasterLayer(parameters, self.CLASS_STACK, context)
        hard_label_layer = self.parameterAsRasterLayer(parameters, self.HARD_LABEL_RASTER, context)
        class_ids_text = self.parameterAsString(parameters, self.CLASS_IDS, context) or ""
        schema = read_class_schema(self.parameterAsFile(parameters, self.CLASS_SCHEMA_CSV, context))
        nodata = self.parameterAsInt(parameters, self.NODATA, context)

        if (write_rasters or write_class_interactions) and ref is None:
            raise QgsProcessingException("Raster helical outputs require a reference grid. Select REF_GRID or disable raster/class-interaction outputs.")
        if write_class_interactions and class_stack_layer is None and hard_label_layer is None:
            raise QgsProcessingException("Class × helical interaction outputs require a class/soft-target stack or a hard label raster.")
        if (write_rasters or write_class_interactions) and ref is not None:
            try:
                from osgeo import gdal
                import numpy as np

                src = gdal.Open(ref.source().split("|", 1)[0])
                if src is None:
                    raise RuntimeError("could not open reference")
                gt, proj, xsize, ysize = src.GetGeoTransform(), src.GetProjection(), src.RasterXSize, src.RasterYSize
                drv = gdal.GetDriverByName("GTiff")
                feature_keys = [k for k in all_feature_names if k not in ("index", "date")]
                # Interactions are meant for cyclic/relative features, not raw year/day metadata.
                interaction_feature_keys = [
                    k for k in feature_keys
                    if k.startswith("sin_") or k.startswith("cos_") or k.startswith("phase_")
                    or k.startswith("delta_") or k in ("t_index", "year_centered")
                ]

                class_arr = None
                class_count = 0
                class_band_names = []
                class_input_mode = "none"
                if write_class_interactions:
                    if class_stack_layer is not None:
                        cds = gdal.Open(class_stack_layer.source().split("|", 1)[0])
                        if cds is None:
                            raise RuntimeError("could not open class/soft-target stack")
                        if cds.RasterXSize != xsize or cds.RasterYSize != ysize:
                            raise RuntimeError("class/soft-target stack must already match the reference grid")
                        class_count = cds.RasterCount
                        for bi in range(1, class_count + 1):
                            desc = cds.GetRasterBand(bi).GetDescription() or f"class_{bi}"
                            class_band_names.append(desc)
                        class_arr = np.stack([cds.GetRasterBand(bi).ReadAsArray().astype("float32") for bi in range(1, class_count + 1)], axis=0)
                        s = class_arr.sum(axis=0, keepdims=True)
                        class_arr = np.where(s > 0, class_arr / np.maximum(s, 1e-12), 0.0).astype("float32")
                        cds = None
                        class_input_mode = "class_stack"
                    else:
                        hds = gdal.Open(hard_label_layer.source().split("|", 1)[0])
                        if hds is None:
                            raise RuntimeError("could not open hard label raster")
                        if hds.RasterXSize != xsize or hds.RasterYSize != ysize:
                            raise RuntimeError("hard label raster must already match the reference grid")
                        hard = hds.GetRasterBand(1).ReadAsArray()
                        hds = None
                        class_ids = load_class_ids(class_ids_text, arrays=None, nodata=nodata) or list(schema.get("class_ids", [])) or load_class_ids("", arrays=[hard], nodata=nodata)
                        if not class_ids:
                            raise RuntimeError("no class IDs could be inferred from the hard label raster")
                        class_names = schema.get("class_names", {})
                        class_count = len(class_ids)
                        class_arr = np.zeros((class_count, ysize, xsize), dtype="float32")
                        for ci, cid in enumerate(class_ids):
                            class_arr[ci] = (hard == int(cid)).astype("float32")
                            class_band_names.append(band_description(cid, class_names, "hard_label"))
                        class_input_mode = "hard_label_auto_onehot"

                for row in rows:
                    if write_rasters:
                        out = os.path.join(out_dir, f"helix_helical_{row['date'].replace('-', '')}.tif")
                        ds = drv.Create(out, xsize, ysize, len(feature_keys), gdal.GDT_Float32, ["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"])
                        ds.SetGeoTransform(gt)
                        ds.SetProjection(proj)
                        for bi, key in enumerate(feature_keys, 1):
                            val = row.get(key, 0)
                            try:
                                val = float(val) if val != "" else -9999.0
                            except Exception:
                                val = -9999.0
                            band = ds.GetRasterBand(bi)
                            band.SetNoDataValue(-9999.0)
                            band.SetDescription(key)
                            band.WriteArray(np.full((ysize, xsize), val, dtype="float32"))
                        ds.FlushCache()
                        ds = None
                        raster_paths.append(out)
                        if load_outputs:
                            add_raster_to_project(out, f"HELIX helical {row['date']}")

                    if write_class_interactions and class_arr is not None:
                        out = os.path.join(out_dir, f"helix_class_helical_interactions_{row['date'].replace('-', '')}.tif")
                        band_count = class_count * len(interaction_feature_keys)
                        ds = drv.Create(out, xsize, ysize, band_count, gdal.GDT_Float32, ["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"])
                        ds.SetGeoTransform(gt)
                        ds.SetProjection(proj)
                        bi = 1
                        for ci in range(class_count):
                            class_label = class_band_names[ci] if ci < len(class_band_names) else f"class_{ci + 1}"
                            for key in interaction_feature_keys:
                                val = row.get(key, 0)
                                try:
                                    val = float(val) if val != "" else 0.0
                                except Exception:
                                    val = 0.0
                                band = ds.GetRasterBand(bi)
                                band.SetNoDataValue(0.0)
                                band.SetDescription(f"{class_label}_x_{key}"[:120])
                                band.WriteArray((class_arr[ci] * val).astype("float32"))
                                bi += 1
                        ds.FlushCache()
                        ds = None
                        interaction_paths.append(out)
                        if load_outputs:
                            add_raster_to_project(out, f"HELIX class×helical {row['date']}")
            except Exception as e:
                raise QgsProcessingException(f"Could not write raster feature stacks: {e}")
        else:
            class_input_mode = "none"

        report = {
            "module": "helical_features",
            "mode": self.MODE_OPTIONS[mode],
            "date_count": len(dates),
            "grid_step_days": grid_step_days,
            "harmonics": max_k,
            "raster_outputs_requested": bool(write_rasters),
            "class_interactions_requested": bool(write_class_interactions),
            "class_interaction_input_mode": class_input_mode,
            "reference_grid_used": bool(ref is not None),
            "features_csv": csv_path,
            "raster_outputs": raster_paths,
            "class_helical_interaction_outputs": interaction_paths,
            "notes": [
                "Helical features are date/feature bands by default, not class bands.",
                "Raster outputs require a reference grid and fail explicitly if it is missing.",
                "Optional class × helical interaction stacks multiply each class/soft-target or internally one-hot hard-label band with cyclic time features for advanced ML workflows.",
            ],
        }
        json_path = os.path.join(out_dir, "helix_helical_report.json")
        write_json(json_path, report)
        write_html(os.path.join(out_dir, "helix_helical_report.html"), "HELIX Helical / Wave Features", [("Summary", f"<pre>{report}</pre>")])
        return {self.OUT_FOLDER: out_dir, self.FEATURES_CSV: csv_path, self.REPORT_JSON: json_path}
