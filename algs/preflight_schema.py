# -*- coding: utf-8 -*-
# Copyright (C) 2026 Sarah Hauser, Karlsruhe Institute of Technology (KIT)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from collections import defaultdict, OrderedDict

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsWkbTypes,
)

from ._utils import (
    resolve_output_folder,
    write_json,
    write_html,
    write_csv,
    read_class_schema,
    safe_feedback,
    make_advanced,
    infer_common_field,
    numeric_class_id,
    next_free_class_id,
    source_value_aliases,
)


class PreflightSchemaAlgorithm(QgsProcessingAlgorithm):
    REF_GRID = "REF_GRID"
    PRIMARY_VECTOR = "PRIMARY_VECTOR"
    VECTOR_LABELS = "VECTOR_LABELS"
    RASTER_LABELS = "RASTER_LABELS"
    CLASS_FIELD = "CLASS_FIELD"
    CLASS_NAME_FIELD = "CLASS_NAME_FIELD"
    DATE_FIELD = "DATE_FIELD"
    VALID_FROM_FIELD = "VALID_FROM_FIELD"
    VALID_TO_FIELD = "VALID_TO_FIELD"
    CLASS_MAP_CSV = "CLASS_MAP_CSV"
    CHECK_GEOMETRY = "CHECK_GEOMETRY"
    SAMPLE_FEATURES = "SAMPLE_FEATURES"
    SAMPLE_CLASSES = "SAMPLE_CLASSES"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    LOAD_REPORT = "LOAD_REPORT"

    OUT_FOLDER = "OUT_FOLDER"
    OUT_JSON = "OUT_JSON"
    OUT_HTML = "OUT_HTML"
    CLASS_SCHEMA = "CLASS_SCHEMA"
    CLASS_SCHEMA_JSON = "CLASS_SCHEMA_JSON"

    def name(self):
        return "preflight_schema"

    def displayName(self):
        return "Preflight & class schema"

    def group(self):
        return "1 Preflight"

    def groupId(self):
        return "01_preflight"

    def shortHelpString(self):
        return (
            "Checks CRS, reference grid, vector/raster inputs, fields and class values before running HELIX. "
            "If a class field contains strings, HELIX maps them to stable integer class IDs and writes the mapping to CSV/JSON. "
            "The schema can be reused by Spatial, Context and Soft Targets modules."
        )

    def createInstance(self):
        return PreflightSchemaAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.REF_GRID, "EO/reference grid raster", optional=True))
        self.addParameter(QgsProcessingParameterVectorLayer(self.PRIMARY_VECTOR, "Primary vector label layer (enables field menus)", [QgsProcessing.TypeVectorAnyGeometry], optional=True))
        self.addParameter(make_advanced(QgsProcessingParameterMultipleLayers(self.VECTOR_LABELS, "Additional vector label layers", QgsProcessing.TypeVectorAnyGeometry, optional=True)))
        self.addParameter(QgsProcessingParameterMultipleLayers(self.RASTER_LABELS, "Raster label layers", QgsProcessing.TypeRaster, optional=True))
        self.addParameter(QgsProcessingParameterField(self.CLASS_FIELD, "Class field", "class", self.PRIMARY_VECTOR, QgsProcessingParameterField.Any, False, True))
        self.addParameter(QgsProcessingParameterField(self.CLASS_NAME_FIELD, "Optional class-name field", "", self.PRIMARY_VECTOR, QgsProcessingParameterField.Any, False, True))
        self.addParameter(make_advanced(QgsProcessingParameterString(self.DATE_FIELD, "Date/snapshot field name", defaultValue="date", optional=True)))
        self.addParameter(make_advanced(QgsProcessingParameterString(self.VALID_FROM_FIELD, "Valid-from field name", defaultValue="valid_from", optional=True)))
        self.addParameter(make_advanced(QgsProcessingParameterString(self.VALID_TO_FIELD, "Valid-to field name", defaultValue="valid_to", optional=True)))
        self.addParameter(make_advanced(QgsProcessingParameterFile(self.CLASS_MAP_CSV, "Optional existing class-map/schema CSV", behavior=QgsProcessingParameterFile.File, extension="csv", optional=True)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.CHECK_GEOMETRY, "Sample geometry validity", defaultValue=True)))
        self.addParameter(make_advanced(QgsProcessingParameterString(self.SAMPLE_FEATURES, "Maximum features sampled for geometry check", defaultValue="500")))
        self.addParameter(make_advanced(QgsProcessingParameterString(self.SAMPLE_CLASSES, "Maximum features sampled for class list; 0 = all", defaultValue="0")))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT_FOLDER, "Output folder"))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.LOAD_REPORT, "Open report after processing", defaultValue=False)))
        self.addOutput(QgsProcessingOutputFolder(self.OUT_FOLDER, "Output folder"))
        self.addOutput(QgsProcessingOutputFile(self.OUT_JSON, "Preflight JSON"))
        self.addOutput(QgsProcessingOutputFile(self.OUT_HTML, "Preflight HTML report"))
        self.addOutput(QgsProcessingOutputFile(self.CLASS_SCHEMA, "Class schema CSV"))
        self.addOutput(QgsProcessingOutputFile(self.CLASS_SCHEMA_JSON, "Class schema JSON"))

    @staticmethod
    def _looks_numeric(value):
        try:
            if value is None:
                return False
            float(value)
            return True
        except Exception:
            return False

    @staticmethod
    def _to_int_if_possible(value):
        try:
            f = float(value)
            if abs(f - int(f)) < 1e-9:
                return int(f)
        except Exception:
            pass
        return None

    def processAlgorithm(self, parameters, context, feedback):
        out_dir = resolve_output_folder(self, parameters, self.OUTPUT_FOLDER, context, "helix_preflight")
        class_field = self.parameterAsString(parameters, self.CLASS_FIELD, context) or "class"
        class_name_field = self.parameterAsString(parameters, self.CLASS_NAME_FIELD, context) or ""
        date_field = self.parameterAsString(parameters, self.DATE_FIELD, context) or "date"
        vf_field = self.parameterAsString(parameters, self.VALID_FROM_FIELD, context) or "valid_from"
        vt_field = self.parameterAsString(parameters, self.VALID_TO_FIELD, context) or "valid_to"
        check_geom = self.parameterAsBool(parameters, self.CHECK_GEOMETRY, context)
        try:
            sample_n = int(float(self.parameterAsString(parameters, self.SAMPLE_FEATURES, context) or 500))
        except Exception:
            sample_n = 500
        try:
            class_sample_n = int(float(self.parameterAsString(parameters, self.SAMPLE_CLASSES, context) or 0))
        except Exception:
            class_sample_n = 0

        ref = self.parameterAsRasterLayer(parameters, self.REF_GRID, context)
        primary_vector = self.parameterAsVectorLayer(parameters, self.PRIMARY_VECTOR, context)
        vectors = []
        if primary_vector is not None:
            vectors.append(primary_vector)
        for v in (self.parameterAsLayerList(parameters, self.VECTOR_LABELS, context) or []):
            if all(v.source() != existing.source() for existing in vectors):
                vectors.append(v)
        rasters = self.parameterAsLayerList(parameters, self.RASTER_LABELS, context) or []
        if vectors and (not class_field or class_field == "class"):
            try:
                class_field = infer_common_field(vectors[0].fields().names(), class_field)
                safe_feedback(feedback, f"Using detected class field: {class_field}")
            except Exception:
                pass

        schema_in = read_class_schema(self.parameterAsFile(parameters, self.CLASS_MAP_CSV, context))
        class_counts = defaultdict(int)
        class_names = dict(schema_in.get("class_names", {}))
        source_to_id = dict(schema_in.get("source_to_id", {}))
        used_class_ids = set(int(c) for c in schema_in.get("class_ids", []))
        used_class_ids.update(int(v) for v in source_to_id.values() if v is not None)
        source_values = {}
        source_types = {}

        # Reserve numeric class IDs before assigning automatic IDs to string labels.
        # This prevents collisions such as numeric class 1 and string class "forest" both becoming ID 1.
        reserved_numeric_ids = set(used_class_ids)
        for v in vectors:
            try:
                fields = [f.name() for f in v.fields()]
                if class_field not in fields:
                    continue
                seen = 0
                for feat in v.getFeatures():
                    if class_sample_n and seen >= class_sample_n:
                        break
                    seen += 1
                    n = numeric_class_id(feat[class_field])
                    if n is not None:
                        reserved_numeric_ids.add(n)
            except Exception:
                pass
        for r in rasters:
            try:
                from osgeo import gdal
                import numpy as np
                ds = gdal.Open(r.source().split("|", 1)[0])
                if ds is not None and ds.RasterCount >= 1:
                    vals = np.unique(ds.GetRasterBand(1).ReadAsArray())
                    if vals.size <= 500:
                        for val in vals.tolist():
                            n = numeric_class_id(val)
                            if n is not None:
                                reserved_numeric_ids.add(n)
                    ds = None
            except Exception:
                pass

        def register_class(raw_value, name_value=None, source_type="vector"):
            if raw_value is None:
                return None
            raw_text = str(raw_value).strip()
            if raw_text == "" or raw_text.lower() == "null":
                return None
            cid = None
            for alias in source_value_aliases(raw_text):
                if alias in source_to_id:
                    cid = int(source_to_id[alias])
                    break
            if cid is None:
                cid = numeric_class_id(raw_text)
                if cid is None:
                    cid = next_free_class_id(used_class_ids, start=max(used_class_ids or {0}) + 1, avoid_ids=reserved_numeric_ids)
                for alias in source_value_aliases(raw_text):
                    source_to_id[alias] = cid
            used_class_ids.add(int(cid))
            class_counts[cid] += 1
            source_values.setdefault(cid, raw_text)
            source_types.setdefault(cid, source_type)
            if name_value is not None and str(name_value).strip() and str(name_value).lower() != "null":
                class_names.setdefault(cid, str(name_value))
            else:
                class_names.setdefault(cid, raw_text if numeric_class_id(raw_text) is None else f"class_{cid}")
            return cid

        report = {"module": "preflight_schema", "status": "ok", "warnings": [], "reference_grid": {}, "vectors": [], "rasters": [], "detected_classes": []}
        if ref:
            ext = ref.extent()
            report["reference_grid"] = {
                "name": ref.name(), "source": ref.source(), "crs": ref.crs().authid(),
                "width": ref.width(), "height": ref.height(),
                "extent": [ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum()],
                "pixel_size_x": ref.rasterUnitsPerPixelX(), "pixel_size_y": ref.rasterUnitsPerPixelY(),
                "band_count": ref.bandCount(),
            }
        else:
            report["warnings"].append("No reference grid selected. Spatial tools require one for EO-grid alignment.")

        for v in vectors:
            fields = [f.name() for f in v.fields()]
            geom_bad = None
            if check_geom:
                bad = 0; checked = 0
                try:
                    for feat in v.getFeatures():
                        if checked >= sample_n:
                            break
                        checked += 1
                        g = feat.geometry()
                        if g and not g.isEmpty() and not g.isGeosValid():
                            bad += 1
                    geom_bad = {"sampled": checked, "invalid": bad}
                except Exception as e:
                    geom_bad = {"error": str(e)}
            missing = [f for f in (class_field, class_name_field, date_field, vf_field, vt_field) if f and f not in fields]
            if class_field and class_field not in fields:
                report["warnings"].append(f"Vector {v.name()}: class field '{class_field}' not found.")
            else:
                seen = 0
                try:
                    for feat in v.getFeatures():
                        if class_sample_n and seen >= class_sample_n:
                            break
                        seen += 1
                        raw = feat[class_field]
                        nm = feat[class_name_field] if class_name_field and class_name_field in fields else None
                        register_class(raw, nm, "vector")
                except Exception as e:
                    report["warnings"].append(f"Vector {v.name()}: could not scan classes ({e}).")
            report["vectors"].append({
                "name": v.name(), "source": v.source(), "crs": v.crs().authid(), "feature_count": v.featureCount(),
                "geometry_type": QgsWkbTypes.displayString(v.wkbType()), "fields": fields,
                "selected_class_field": class_field, "selected_class_name_field": class_name_field,
                "missing_requested_fields": missing, "geometry_check": geom_bad,
            })

        # Raster class scan: best effort, first band only. Supports categorical integer labels.
        for r in rasters:
            ext = r.extent()
            crs_warn = bool(ref and r.crs() != ref.crs())
            if crs_warn:
                report["warnings"].append(f"Raster {r.name()}: CRS differs from reference grid; it will need reprojection/resampling.")
            unique_values = []
            try:
                from osgeo import gdal
                import numpy as np
                ds = gdal.Open(r.source().split("|", 1)[0])
                if ds is not None and ds.RasterCount >= 1:
                    arr = ds.GetRasterBand(1).ReadAsArray()
                    vals = np.unique(arr)
                    # avoid enormous schemas from continuous rasters
                    if vals.size <= 500:
                        for val in vals.tolist():
                            cid = self._to_int_if_possible(val)
                            if cid is not None and cid != 0:
                                register_class(cid, None, "raster")
                                unique_values.append(cid)
                    else:
                        report["warnings"].append(f"Raster {r.name()}: more than 500 unique values; not treated as categorical class raster in preflight.")
                    ds = None
            except Exception as e:
                report["warnings"].append(f"Raster {r.name()}: could not scan class values ({e}).")
            report["rasters"].append({
                "name": r.name(), "source": r.source(), "crs": r.crs().authid(), "width": r.width(), "height": r.height(),
                "extent": [ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum()],
                "pixel_size_x": r.rasterUnitsPerPixelX(), "pixel_size_y": r.rasterUnitsPerPixelY(), "band_count": r.bandCount(),
                "crs_differs_from_ref": crs_warn, "unique_values_first_band_sample": unique_values[:100],
            })

        class_rows = []
        all_ids = sorted(set(class_counts.keys()) | set(schema_in.get("class_ids", [])))
        for cid in all_ids:
            schema_include = schema_in.get("include", {}).get(cid, True)
            schema_merge = schema_in.get("merge_to", {}).get(cid, cid)
            schema_priority = schema_in.get("priority", {}).get(cid, 1.0)
            schema_q = schema_in.get("quality_q", {}).get(cid, 1.0)
            class_rows.append({
                "class_id": cid,
                "class_name": class_names.get(cid, f"class_{cid}"),
                "source_value": source_values.get(cid, str(cid)),
                "source_type": source_types.get(cid, "schema"),
                "include": 1 if schema_include else 0,
                "merge_to": schema_merge,
                "priority": schema_priority,
                "quality_q": schema_q,
                "feature_or_pixel_count_sample": int(class_counts.get(cid, 0)),
            })
        schema_csv = os.path.join(out_dir, "helix_class_schema.csv")
        schema_json = os.path.join(out_dir, "helix_class_schema.json")
        fields = ["class_id", "class_name", "source_value", "source_type", "include", "merge_to", "priority", "quality_q", "feature_or_pixel_count_sample"]
        write_csv(schema_csv, class_rows, fields)
        write_json(schema_json, {"schema_version": "HELIX_CLASS_SCHEMA_V1", "classes": class_rows})
        report["detected_classes"] = class_rows
        report["class_schema_csv"] = schema_csv
        report["class_schema_json"] = schema_json

        json_path = os.path.join(out_dir, "helix_preflight.json")
        html_path = os.path.join(out_dir, "helix_preflight.html")
        write_json(json_path, report)
        warn_html = "<p class='ok'>No warnings.</p>" if not report["warnings"] else "<ul>" + "".join(f"<li class='warn'>{w}</li>" for w in report["warnings"]) + "</ul>"
        class_html = "<p>No classes detected. Check the class field or use a class schema CSV.</p>" if not class_rows else "<table><tr><th>ID</th><th>Name</th><th>Source value</th><th>Include</th><th>Merge to</th><th>Sample count</th></tr>" + "".join(f"<tr><td>{r['class_id']}</td><td>{r['class_name']}</td><td>{r['source_value']}</td><td>{r['include']}</td><td>{r['merge_to']}</td><td>{r['feature_or_pixel_count_sample']}</td></tr>" for r in class_rows) + "</table>"
        write_html(html_path, "HELIX Preflight & Class Schema", [
            ("Warnings", warn_html),
            ("Reference grid", "<pre>" + str(report["reference_grid"]) + "</pre>"),
            ("Detected class schema", class_html + f"<p>CSV: <code>{schema_csv}</code><br>JSON: <code>{schema_json}</code></p>"),
            ("Vector labels", "<pre>" + str(report["vectors"]) + "</pre>"),
            ("Raster labels", "<pre>" + str(report["rasters"]) + "</pre>"),
        ])
        safe_feedback(feedback, f"Wrote class schema: {schema_csv}")
        return {self.OUT_FOLDER: out_dir, self.OUT_JSON: json_path, self.OUT_HTML: html_path, self.CLASS_SCHEMA: schema_csv, self.CLASS_SCHEMA_JSON: schema_json}
