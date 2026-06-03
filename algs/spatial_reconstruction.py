# -*- coding: utf-8 -*-
# Copyright (C) 2026 Sarah Hauser, Karlsruhe Institute of Technology (KIT)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import csv
import os
from pathlib import Path

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
)

from ._utils import (
    add_raster_to_project,
    layer_source,
    strip_provider_uri,
    load_class_ids,
    resolve_output_folder,
    safe_feedback,
    write_csv,
    write_html,
    write_json,
    make_advanced,
    infer_common_field,
    read_class_schema,
    band_description,
    numeric_class_id,
    next_free_class_id,
    source_value_aliases,
)


class SpatialReconstructionAlgorithm(QgsProcessingAlgorithm):
    REF_GRID = "REF_GRID"
    PRIMARY_VECTOR = "PRIMARY_VECTOR"
    VECTOR_LABELS = "VECTOR_LABELS"
    RASTER_LABELS = "RASTER_LABELS"
    CLASS_FIELD = "CLASS_FIELD"
    CLASS_NAME_FIELD = "CLASS_NAME_FIELD"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    METHOD = "METHOD"
    FUSION_RULE = "FUSION_RULE"
    CLASS_IDS = "CLASS_IDS"
    CLASS_MAP_CSV = "CLASS_MAP_CSV"
    CLASS_SELECTION = "CLASS_SELECTION"
    ALL_TOUCHED = "ALL_TOUCHED"
    SUPERSAMPLE = "SUPERSAMPLE"
    MIN_COVERAGE = "MIN_COVERAGE"
    RESAMPLING = "RESAMPLING"
    NODATA = "NODATA"
    BACKGROUND_CLASS = "BACKGROUND_CLASS"
    WRITE_PROBABILITIES = "WRITE_PROBABILITIES"
    WRITE_CLASS_STACK = "WRITE_CLASS_STACK"
    WRITE_COVERAGE = "WRITE_COVERAGE"
    WRITE_AGREEMENT = "WRITE_AGREEMENT"
    WRITE_SOURCE_STACK = "WRITE_SOURCE_STACK"
    WRITE_PURITY = "WRITE_PURITY"
    WRITE_INTERMEDIATE = "WRITE_INTERMEDIATE"
    LOAD_OUTPUTS = "LOAD_OUTPUTS"

    OUT_FOLDER = "OUT_FOLDER"
    HARD_LABEL = "HARD_LABEL"
    PROB_STACK = "PROB_STACK"
    CLASS_STACK = "CLASS_STACK"
    COVERAGE = "COVERAGE"
    SOURCE_AGREEMENT = "SOURCE_AGREEMENT"
    SOURCE_LABEL_STACK = "SOURCE_LABEL_STACK"
    PURITY = "PURITY"
    CLASS_SCHEMA = "CLASS_SCHEMA"
    CLASS_SCHEMA_JSON = "CLASS_SCHEMA_JSON"
    REPORT_JSON = "REPORT_JSON"

    METHOD_OPTIONS = [
        "Auto / minimal: align labels to EO-grid hard raster",
        "Vector hard rasterization",
        "Vector source-vote probability support",
        "Raster align/merge to reference grid",
        "Vector + raster fusion",
        "QA only / dry run",
    ]
    FUSION_OPTIONS = [
        "First valid source wins",
        "Last valid source wins",
        "Majority vote",
        "Maximum class-weighted support (schema priority × quality)",
    ]
    CLASS_SELECTION_OPTIONS = [
        "Use all detected classes",
        "Use CLASS_IDS only",
        "Use included classes from schema CSV",
    ]
    RESAMPLING_OPTIONS = ["Nearest neighbour (categorical)", "Mode / majority (categorical; fallback nearest if unavailable)"]

    def name(self):
        return "spatial_reconstruction"

    def displayName(self):
        return "Spatial reconstruction: labels → EO-grid raster"

    def group(self):
        return "2 Spatial"

    def groupId(self):
        return "02_spatial"

    def shortHelpString(self):
        return (
            "Standalone spatial label alignment. Default output is one single-band hard class-ID raster plus schema/report. "
            "String class attributes are mapped automatically to integer class IDs and stored in helix_class_schema CSV/JSON. "
            "Optional advanced outputs include one-hot class stack, class probability/support stack, source-label stack, coverage, agreement and purity."
        )

    def createInstance(self):
        return SpatialReconstructionAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.REF_GRID, "EO/reference grid raster"))
        self.addParameter(QgsProcessingParameterVectorLayer(self.PRIMARY_VECTOR, "Primary vector label layer (enables field menus)", [QgsProcessing.TypeVectorAnyGeometry], optional=True))
        self.addParameter(make_advanced(QgsProcessingParameterMultipleLayers(self.VECTOR_LABELS, "Additional vector label layers", QgsProcessing.TypeVectorAnyGeometry, optional=True)))
        self.addParameter(QgsProcessingParameterMultipleLayers(self.RASTER_LABELS, "Raster label layers", QgsProcessing.TypeRaster, optional=True))
        self.addParameter(QgsProcessingParameterField(self.CLASS_FIELD, "Class field", "class", self.PRIMARY_VECTOR, QgsProcessingParameterField.Any, False, True))
        self.addParameter(QgsProcessingParameterField(self.CLASS_NAME_FIELD, "Optional class-name field", "", self.PRIMARY_VECTOR, QgsProcessingParameterField.Any, False, True))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT_FOLDER, "Output folder"))

        self.addParameter(make_advanced(QgsProcessingParameterEnum(self.METHOD, "Spatial method", self.METHOD_OPTIONS, defaultValue=0)))
        self.addParameter(make_advanced(QgsProcessingParameterEnum(self.FUSION_RULE, "Fusion rule for multiple sources", self.FUSION_OPTIONS, defaultValue=2)))
        self.addParameter(make_advanced(QgsProcessingParameterEnum(self.CLASS_SELECTION, "Class selection", self.CLASS_SELECTION_OPTIONS, defaultValue=0)))
        self.addParameter(make_advanced(QgsProcessingParameterString(self.CLASS_IDS, "Class IDs, comma-separated; empty = infer", defaultValue="", optional=True)))
        self.addParameter(make_advanced(QgsProcessingParameterFile(self.CLASS_MAP_CSV, "Optional class-schema/map CSV", behavior=QgsProcessingParameterFile.File, extension="csv", optional=True)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.ALL_TOUCHED, "All touched pixels for vectors", defaultValue=True)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.SUPERSAMPLE, "Compatibility placeholder: supersampling factor (not applied in this release)", type=QgsProcessingParameterNumber.Integer, minValue=1, maxValue=12, defaultValue=3)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.MIN_COVERAGE, "Minimum valid/source coverage", type=QgsProcessingParameterNumber.Double, minValue=0.0, maxValue=1.0, defaultValue=0.01)))
        self.addParameter(make_advanced(QgsProcessingParameterEnum(self.RESAMPLING, "Raster resampling", self.RESAMPLING_OPTIONS, defaultValue=0)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.NODATA, "NoData/background value", type=QgsProcessingParameterNumber.Integer, defaultValue=0)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.BACKGROUND_CLASS, "Final background / no-label value", type=QgsProcessingParameterNumber.Integer, defaultValue=0)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_CLASS_STACK, "Write one-hot class stack", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_PROBABILITIES, "Write class probability/support stack", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_COVERAGE, "Write source coverage raster", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_AGREEMENT, "Write source-agreement raster", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_SOURCE_STACK, "Write per-source label stack (one band per input source)", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_PURITY, "Write spatial purity / dominance raster", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_INTERMEDIATE, "Keep intermediate source rasters", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.LOAD_OUTPUTS, "Load generated spatial outputs into QGIS", defaultValue=True)))

        self.addOutput(QgsProcessingOutputFolder(self.OUT_FOLDER, "Output folder"))
        self.addOutput(QgsProcessingOutputFile(self.HARD_LABEL, "Hard label raster"))
        self.addOutput(QgsProcessingOutputFile(self.PROB_STACK, "Optional class probability/support stack"))
        self.addOutput(QgsProcessingOutputFile(self.CLASS_STACK, "Optional one-hot class stack"))
        self.addOutput(QgsProcessingOutputFile(self.COVERAGE, "Optional source coverage raster"))
        self.addOutput(QgsProcessingOutputFile(self.SOURCE_AGREEMENT, "Optional source-agreement raster"))
        self.addOutput(QgsProcessingOutputFile(self.SOURCE_LABEL_STACK, "Optional per-source label stack"))
        self.addOutput(QgsProcessingOutputFile(self.PURITY, "Optional spatial purity/dominance raster"))
        self.addOutput(QgsProcessingOutputFile(self.CLASS_SCHEMA, "Detected class schema CSV"))
        self.addOutput(QgsProcessingOutputFile(self.CLASS_SCHEMA_JSON, "Detected class schema JSON"))
        self.addOutput(QgsProcessingOutputFile(self.REPORT_JSON, "Report JSON"))

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
        try:
            from osgeo import gdal, ogr, osr
            import numpy as np
        except Exception as e:
            raise QgsProcessingException(f"HELIX spatial reconstruction needs GDAL/OGR and NumPy in QGIS Python. Import failed: {e}")

        ref_layer = self.parameterAsRasterLayer(parameters, self.REF_GRID, context)
        if ref_layer is None:
            raise QgsProcessingException("Reference grid is required.")
        ref_path = strip_provider_uri(ref_layer.source())
        ref_ds = gdal.Open(ref_path)
        if ref_ds is None:
            raise QgsProcessingException(f"Could not open reference raster: {ref_path}")

        out_dir = resolve_output_folder(self, parameters, self.OUTPUT_FOLDER, context, "helix_spatial")
        method = self.parameterAsEnum(parameters, self.METHOD, context)
        fusion_rule = self.parameterAsEnum(parameters, self.FUSION_RULE, context)
        class_selection = self.parameterAsEnum(parameters, self.CLASS_SELECTION, context)
        class_field = self.parameterAsString(parameters, self.CLASS_FIELD, context) or "class"
        class_name_field = self.parameterAsString(parameters, self.CLASS_NAME_FIELD, context) or ""
        all_touched = self.parameterAsBool(parameters, self.ALL_TOUCHED, context)
        supersample = self.parameterAsInt(parameters, self.SUPERSAMPLE, context)
        nodata = self.parameterAsInt(parameters, self.NODATA, context)
        background_class = self.parameterAsInt(parameters, self.BACKGROUND_CLASS, context)
        if supersample and supersample != 1:
            safe_feedback(feedback, "Supersampling is a compatibility placeholder in this release and is not applied; categorical alignment uses GDAL rasterize/warp.")
        write_class_stack = self.parameterAsBool(parameters, self.WRITE_CLASS_STACK, context)
        write_prob = self.parameterAsBool(parameters, self.WRITE_PROBABILITIES, context) or method == 2
        write_cov = self.parameterAsBool(parameters, self.WRITE_COVERAGE, context)
        write_agree = self.parameterAsBool(parameters, self.WRITE_AGREEMENT, context)
        write_source_stack = self.parameterAsBool(parameters, self.WRITE_SOURCE_STACK, context)
        write_purity = self.parameterAsBool(parameters, self.WRITE_PURITY, context)
        keep_intermediate = self.parameterAsBool(parameters, self.WRITE_INTERMEDIATE, context)
        load_outputs = self.parameterAsBool(parameters, self.LOAD_OUTPUTS, context)
        resampling_idx = self.parameterAsEnum(parameters, self.RESAMPLING, context)
        min_coverage = float(self.parameterAsDouble(parameters, self.MIN_COVERAGE, context))
        resample_alg = "near" if resampling_idx == 0 else "mode"

        primary_vector = self.parameterAsVectorLayer(parameters, self.PRIMARY_VECTOR, context)
        vectors = []
        if primary_vector is not None:
            vectors.append(primary_vector)
        for v in (self.parameterAsLayerList(parameters, self.VECTOR_LABELS, context) or []):
            if all(layer_source(v) != layer_source(existing) for existing in vectors):
                vectors.append(v)
        rasters = self.parameterAsLayerList(parameters, self.RASTER_LABELS, context) or []
        if not vectors and not rasters:
            raise QgsProcessingException("Select at least one vector or raster label source.")
        if vectors and (not class_field or class_field == "class"):
            try:
                class_field = infer_common_field(vectors[0].fields().names(), class_field)
                safe_feedback(feedback, f"Using detected class field: {class_field}")
            except Exception:
                pass

        gt = ref_ds.GetGeoTransform(); proj = ref_ds.GetProjection(); xsize, ysize = ref_ds.RasterXSize, ref_ds.RasterYSize
        xmin, ymax = gt[0], gt[3]
        xmax, ymin = xmin + gt[1] * xsize, ymax + gt[5] * ysize
        bounds = (xmin, ymin, xmax, ymax)
        drv = gdal.GetDriverByName("GTiff")

        schema_in = read_class_schema(self.parameterAsFile(parameters, self.CLASS_MAP_CSV, context))
        class_names = dict(schema_in.get("class_names", {}))
        include_map = dict(schema_in.get("include", {}))
        merge_map = dict(schema_in.get("merge_to", {}))
        source_to_id = dict(schema_in.get("source_to_id", {}))
        quality_map = dict(schema_in.get("quality_q", {}))
        priority_map = dict(schema_in.get("priority", {}))
        used_class_ids = set(int(c) for c in schema_in.get("class_ids", []))
        used_class_ids.update(int(v) for v in source_to_id.values() if v is not None)
        source_values = {}
        source_types = {}
        remap_events = []

        # Reserve numeric class IDs before assigning automatic IDs to string labels.
        # This prevents mixed numeric/string schemas from collapsing into the same class ID.
        reserved_numeric_ids = set(used_class_ids)
        for v in vectors:
            try:
                fields = v.fields().names()
                if class_field not in fields:
                    continue
                for feat in v.getFeatures():
                    n = numeric_class_id(feat[class_field])
                    if n is not None:
                        reserved_numeric_ids.add(n)
            except Exception:
                pass
        for r in rasters:
            try:
                ds = gdal.Open(strip_provider_uri(layer_source(r)))
                if ds is not None and ds.RasterCount >= 1:
                    vals = np.unique(ds.GetRasterBand(1).ReadAsArray())
                    if vals.size <= 5000:
                        for val in vals.tolist():
                            n = numeric_class_id(val)
                            if n is not None and n != int(nodata):
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
                    cid = next_free_class_id(used_class_ids, start=max(used_class_ids or {0}) + 1, avoid_ids=reserved_numeric_ids | {nodata, background_class})
                for alias in source_value_aliases(raw_text):
                    source_to_id[alias] = cid
            used_class_ids.add(int(cid))
            mapped_cid = int(merge_map.get(cid, cid))
            if mapped_cid != cid:
                used_class_ids.add(mapped_cid)
            source_values.setdefault(mapped_cid, raw_text)
            source_types.setdefault(mapped_cid, source_type)
            if name_value is not None and str(name_value).strip() and str(name_value).lower() != "null":
                class_names.setdefault(mapped_cid, str(name_value))
            else:
                class_names.setdefault(mapped_cid, raw_text if numeric_class_id(raw_text) is None else f"class_{mapped_cid}")
            include_map.setdefault(mapped_cid, include_map.get(cid, True))
            quality_map.setdefault(mapped_cid, quality_map.get(cid, 1.0))
            priority_map.setdefault(mapped_cid, priority_map.get(cid, 1.0))
            return mapped_cid

        def remap_raster_array(arr, source_name="raster"):
            """Apply class-schema source_value -> class_id mapping to categorical raster values."""
            out = arr.copy().astype("int32")
            mapped_any = False
            if source_to_id:
                mapped = np.full(out.shape, nodata, dtype="int32")
                for raw_alias, cid in list(source_to_id.items()):
                    raw_int = numeric_class_id(raw_alias)
                    if raw_int is None:
                        continue
                    target = int(merge_map.get(int(cid), int(cid)))
                    m = out == int(raw_int)
                    if np.any(m):
                        mapped[m] = target
                        mapped_any = True
                        source_values.setdefault(target, str(raw_alias))
                        source_types.setdefault(target, "raster")
                        include_map.setdefault(target, include_map.get(int(cid), True))
                        quality_map.setdefault(target, quality_map.get(int(cid), 1.0))
                        priority_map.setdefault(target, priority_map.get(int(cid), 1.0))
                if mapped_any:
                    keep_unknown = (mapped == nodata) & (out != nodata)
                    mapped[keep_unknown] = out[keep_unknown]
                    out = mapped
                    remap_events.append({"source": source_name, "schema_value_mapping_applied": True})
            # Register remaining numeric categories after remapping, so schema rows/report stay complete.
            try:
                vals = np.unique(out)
                if vals.size <= 5000:
                    for val in vals.tolist():
                        n = numeric_class_id(val)
                        if n is None or n in (int(nodata), int(background_class)):
                            continue
                        register_class(n, None, "raster")
            except Exception:
                pass
            return out

        # Pre-scan vector classes so string labels have stable numeric IDs before rasterization.
        for v in vectors:
            fields = v.fields().names()
            if class_field not in fields:
                continue
            for feat in v.getFeatures():
                nm = feat[class_name_field] if class_name_field and class_name_field in fields else None
                register_class(feat[class_field], nm, "vector")

        def create_like(path, dtype=gdal.GDT_Int32, bands=1, nodata_value=None):
            ds = drv.Create(path, xsize, ysize, bands, dtype, ["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"])
            if ds is None:
                raise QgsProcessingException(f"Could not create output raster: {path}")
            ds.SetGeoTransform(gt); ds.SetProjection(proj)
            nd = nodata if nodata_value is None else nodata_value
            for b in range(1, bands + 1):
                ds.GetRasterBand(b).SetNoDataValue(nd)
            return ds

        def mapped_vector_copy(vlayer, out_path):
            raw_src = layer_source(vlayer)
            src = strip_provider_uri(raw_src)
            layer_name = None
            if "|" in str(raw_src):
                for part in str(raw_src).split("|")[1:]:
                    if part.startswith("layername="):
                        layer_name = part.split("=", 1)[1]
                        break
            vds = ogr.Open(src)
            if vds is None:
                raise QgsProcessingException(f"Could not open vector layer: {src}")
            lyr = vds.GetLayerByName(layer_name) if layer_name else vds.GetLayer(0)
            if lyr is None:
                raise QgsProcessingException(f"Could not read vector layer '{layer_name or 0}' from: {src}")
            field_names = [lyr.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(lyr.GetLayerDefn().GetFieldCount())]
            if class_field not in field_names:
                # create a layer that burns value 1 if field missing
                safe_feedback(feedback, f"Class field '{class_field}' not found in {vlayer.name()}; burning value 1.")
            gpkg_drv = ogr.GetDriverByName("GPKG")
            if os.path.exists(out_path):
                gpkg_drv.DeleteDataSource(out_path)
            out_ds = gpkg_drv.CreateDataSource(out_path)
            srs = lyr.GetSpatialRef()
            out_lyr = out_ds.CreateLayer("mapped", srs=srs, geom_type=lyr.GetGeomType())
            out_lyr.CreateField(ogr.FieldDefn("HELIX_ID", ogr.OFTInteger))
            out_defn = out_lyr.GetLayerDefn()
            for feat in lyr:
                raw = feat.GetField(class_field) if class_field in field_names else 1
                name_val = feat.GetField(class_name_field) if class_name_field and class_name_field in field_names else None
                cid = register_class(raw, name_val, "vector") or 1
                if not include_map.get(cid, True):
                    continue
                cid = int(merge_map.get(cid, cid))
                out_feat = ogr.Feature(out_defn)
                out_feat.SetField("HELIX_ID", cid)
                geom = feat.GetGeometryRef()
                if geom is not None:
                    out_feat.SetGeometry(geom.Clone())
                    out_lyr.CreateFeature(out_feat)
                out_feat = None
            out_ds.FlushCache(); out_ds = None; vds = None
            return out_path

        def rasterize_vector(vlayer, out_path, mapped_path):
            mapped_vector_copy(vlayer, mapped_path)
            kwargs = dict(
                format="GTiff", outputSRS=proj, outputBounds=bounds, width=xsize, height=ysize,
                noData=nodata, initValues=nodata, outputType=gdal.GDT_Int32,
                allTouched=all_touched, attribute="HELIX_ID",
                creationOptions=["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"],
            )
            res = gdal.Rasterize(out_path, mapped_path, options=gdal.RasterizeOptions(**kwargs))
            if res is None:
                raise QgsProcessingException(f"GDAL rasterize failed for mapped vector: {mapped_path}")
            res.FlushCache(); res = None
            return out_path

        def align_raster(rlayer, out_path):
            src = strip_provider_uri(layer_source(rlayer))
            try:
                res = gdal.Warp(out_path, src, format="GTiff", dstSRS=proj, outputBounds=bounds, width=xsize, height=ysize, srcNodata=nodata, dstNodata=nodata, resampleAlg=resample_alg, multithread=True, creationOptions=["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"])
            except Exception:
                res = gdal.Warp(out_path, src, format="GTiff", dstSRS=proj, outputBounds=bounds, width=xsize, height=ysize, srcNodata=nodata, dstNodata=nodata, resampleAlg="near", multithread=True, creationOptions=["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"])
            if res is None:
                raise QgsProcessingException(f"GDAL warp failed for {src}")
            res.FlushCache(); res = None
            return out_path

        if method == 5:
            report = {"module": "spatial_reconstruction", "mode": "QA only", "vectors": [v.name() for v in vectors], "rasters": [r.name() for r in rasters], "reference_grid": ref_path}
            json_path = os.path.join(out_dir, "helix_spatial_report.json")
            write_json(json_path, report)
            write_html(os.path.join(out_dir, "helix_spatial_report.html"), "HELIX Spatial Reconstruction QA", [("Inputs", f"<pre>{report}</pre>")])
            return {self.OUT_FOLDER: out_dir, self.REPORT_JSON: json_path, self.HARD_LABEL: "", self.PROB_STACK: "", self.CLASS_STACK: "", self.COVERAGE: "", self.SOURCE_AGREEMENT: "", self.SOURCE_LABEL_STACK: "", self.PURITY: "", self.CLASS_SCHEMA: "", self.CLASS_SCHEMA_JSON: ""}

        created_sources = []; source_meta = []
        tmp_dir = os.path.join(out_dir, "_sources"); os.makedirs(tmp_dir, exist_ok=True)
        for i, v in enumerate(vectors, 1):
            out = os.path.join(tmp_dir, f"source_vector_{i:02d}.tif")
            mapped = os.path.join(tmp_dir, f"source_vector_{i:02d}_mapped.gpkg")
            safe_feedback(feedback, f"Rasterizing vector {i}/{len(vectors)}: {v.name()}")
            created_sources.append(rasterize_vector(v, out, mapped))
            source_meta.append({"type": "vector", "name": v.name(), "path": out, "mapped_vector": mapped})
        for i, r in enumerate(rasters, 1):
            out = os.path.join(tmp_dir, f"source_raster_{i:02d}_aligned.tif")
            safe_feedback(feedback, f"Aligning raster {i}/{len(rasters)}: {r.name()}")
            created_sources.append(align_raster(r, out))
            source_meta.append({"type": "raster", "name": r.name(), "path": out, "resampling": self.RESAMPLING_OPTIONS[resampling_idx]})

        arrays = []
        for p in created_sources:
            ds = gdal.Open(p)
            if ds is None:
                raise QgsProcessingException(f"Could not reopen source raster {p}")
            arr = ds.GetRasterBand(1).ReadAsArray().astype("int32"); ds = None
            src_name = source_meta[len(arrays)].get("name", os.path.basename(p)) if len(arrays) < len(source_meta) else os.path.basename(p)
            arr = remap_raster_array(arr, src_name)
            if merge_map:
                out_arr = arr.copy()
                for old, new in merge_map.items():
                    out_arr[arr == int(old)] = int(new)
                arr = out_arr
            arrays.append(arr)
        if not arrays:
            raise QgsProcessingException("No source rasters were created/aligned.")

        stack = np.stack(arrays, axis=0)
        valid = stack != nodata
        valid_count = valid.sum(axis=0).astype("float32")
        source_coverage = np.clip(valid_count / float(max(len(arrays), 1)), 0, 1).astype("float32")
        class_text = self.parameterAsString(parameters, self.CLASS_IDS, context) or ""
        detected_class_ids = load_class_ids(class_text, arrays=arrays, nodata=nodata)
        detected_class_ids = sorted(set(detected_class_ids) | set(int(c) for c in source_values.keys()))
        if class_selection == 2:
            schema_ids = set(int(c) for c in schema_in.get("class_ids", []))
            detected_class_ids = [cid for cid in detected_class_ids if int(cid) in schema_ids and include_map.get(int(cid), True)]
        elif class_selection == 1 and class_text:
            detected_class_ids = load_class_ids(class_text, arrays=None, nodata=nodata)
        if not detected_class_ids:
            raise QgsProcessingException("No class IDs found. Provide CLASS_IDS, a schema CSV, or check source values/class field.")
        class_ids = sorted(dict.fromkeys(int(c) for c in detected_class_ids if int(c) not in (int(nodata), int(background_class))))

        allowed = set(class_ids)
        stack_masked = stack.copy()
        stack_masked[~np.isin(stack_masked, list(allowed))] = nodata
        valid = stack_masked != nodata
        valid_count = valid.sum(axis=0).astype("float32")
        support_ok = (valid_count / float(max(len(arrays), 1))) >= min_coverage

        if fusion_rule == 0:
            hard = np.full((ysize, xsize), nodata, dtype="int32")
            for arr in stack_masked:
                m = (hard == nodata) & (arr != nodata); hard[m] = arr[m]
            max_count = np.where(hard != nodata, 1, 0).astype("float32")
            agreement_denominator = valid_count
        elif fusion_rule == 1:
            hard = np.full((ysize, xsize), nodata, dtype="int32")
            for arr in stack_masked:
                m = arr != nodata; hard[m] = arr[m]
            max_count = np.where(hard != nodata, 1, 0).astype("float32")
            agreement_denominator = valid_count
        elif fusion_rule == 3:
            class_weights = np.array([float(priority_map.get(cid, 1.0)) * float(quality_map.get(cid, 1.0)) for cid in class_ids], dtype="float32")
            weighted_counts = [((stack_masked == cid).astype("float32") * class_weights[i]).sum(axis=0) for i, cid in enumerate(class_ids)]
            count_stack = np.stack(weighted_counts, axis=0)
            max_idx = np.argmax(count_stack, axis=0)
            max_count = np.max(count_stack, axis=0).astype("float32")
            hard = np.array(class_ids, dtype="int32")[max_idx]
            hard[max_count == 0] = nodata
            source_weight_stack = np.zeros_like(stack_masked, dtype="float32")
            for i, cid in enumerate(class_ids):
                source_weight_stack[stack_masked == cid] = class_weights[i]
            agreement_denominator = source_weight_stack.sum(axis=0).astype("float32")
        else:
            counts = [(stack_masked == cid).sum(axis=0) for cid in class_ids]
            count_stack = np.stack(counts, axis=0)
            max_idx = np.argmax(count_stack, axis=0)
            max_count = np.max(count_stack, axis=0).astype("float32")
            hard = np.array(class_ids, dtype="int32")[max_idx]
            hard[max_count == 0] = nodata
            agreement_denominator = valid_count
        hard[~support_ok] = background_class
        hard[(hard == nodata) & support_ok] = background_class

        hard_path = os.path.join(out_dir, "helix_label_hard.tif")
        ds = create_like(hard_path, gdal.GDT_Int32, 1, nodata_value=background_class); b = ds.GetRasterBand(1); b.SetDescription("hard_class_id"); b.WriteArray(hard); ds.FlushCache(); ds = None

        source_stack_path = ""
        if write_source_stack:
            source_stack_path = os.path.join(out_dir, "helix_spatial_source_labels.tif")
            ds = create_like(source_stack_path, gdal.GDT_Int32, len(arrays), nodata_value=nodata)
            for bi, arr in enumerate(stack_masked, 1):
                src_name = source_meta[bi - 1].get("name", f"source_{bi}") if bi - 1 < len(source_meta) else f"source_{bi}"
                b = ds.GetRasterBand(bi); b.SetDescription(f"source_{bi}_{src_name}"); b.WriteArray(arr.astype("int32"))
            ds.FlushCache(); ds = None

        class_stack_path = ""
        if write_class_stack:
            class_stack_path = os.path.join(out_dir, "helix_spatial_class_stack.tif")
            ds = create_like(class_stack_path, gdal.GDT_Byte, len(class_ids), nodata_value=0)
            for bi, cid in enumerate(class_ids, 1):
                b = ds.GetRasterBand(bi); b.SetNoDataValue(0); b.SetDescription(band_description(cid, class_names, "onehot")); b.WriteArray(((hard == cid) & (hard != nodata)).astype("uint8"))
            ds.FlushCache(); ds = None

        prob_path = ""
        if write_prob:
            prob_path = os.path.join(out_dir, "helix_spatial_probabilities.tif")
            ds = create_like(prob_path, gdal.GDT_Float32, len(class_ids), nodata_value=0)
            for bi, cid in enumerate(class_ids, 1):
                with np.errstate(divide="ignore", invalid="ignore"):
                    prob = np.where(valid_count > 0, (stack_masked == cid).sum(axis=0).astype("float32") / np.maximum(valid_count, 1.0), 0.0)
                b = ds.GetRasterBand(bi); b.SetNoDataValue(0); b.SetDescription(band_description(cid, class_names, "support")); b.WriteArray(prob.astype("float32"))
            ds.FlushCache(); ds = None

        coverage_path = ""
        if write_cov:
            coverage_path = os.path.join(out_dir, "helix_spatial_coverage.tif")
            ds = create_like(coverage_path, gdal.GDT_Float32, 1, nodata_value=0); b = ds.GetRasterBand(1); b.SetDescription("source_coverage_fraction"); b.WriteArray(source_coverage.astype("float32")); ds.FlushCache(); ds = None

        agreement_path = ""; agreement = None
        if write_agree or write_purity:
            with np.errstate(divide="ignore", invalid="ignore"):
                agreement = np.where(agreement_denominator > 0, max_count / np.maximum(agreement_denominator, 1e-12), 0.0).astype("float32")
        if write_agree:
            agreement_path = os.path.join(out_dir, "helix_spatial_source_agreement.tif")
            ds = create_like(agreement_path, gdal.GDT_Float32, 1, nodata_value=0); b = ds.GetRasterBand(1); b.SetDescription("source_agreement_top_class_fraction"); b.WriteArray(agreement); ds.FlushCache(); ds = None

        purity_path = ""
        if write_purity:
            purity_path = os.path.join(out_dir, "helix_spatial_purity.tif")
            ds = create_like(purity_path, gdal.GDT_Float32, 1, nodata_value=0); b = ds.GetRasterBand(1); b.SetDescription("spatial_purity_top_class_fraction"); b.WriteArray((agreement if agreement is not None else np.zeros((ysize, xsize), dtype="float32"))); ds.FlushCache(); ds = None

        class_rows = []
        for cid in class_ids:
            class_rows.append({
                "class_id": cid,
                "class_name": class_names.get(cid, f"class_{cid}"),
                "source_value": source_values.get(cid, str(cid)),
                "source_type": source_types.get(cid, "raster_or_schema"),
                "include": 1 if include_map.get(cid, True) else 0,
                "merge_to": merge_map.get(cid, cid),
                "priority": priority_map.get(cid, 1.0),
                "quality_q": quality_map.get(cid, 1.0),
                "pixel_count": int((hard == cid).sum()),
            })
        schema_csv = os.path.join(out_dir, "helix_class_schema_detected.csv")
        schema_json = os.path.join(out_dir, "helix_class_schema_detected.json")
        fieldnames = ["class_id", "class_name", "source_value", "source_type", "include", "merge_to", "priority", "quality_q", "pixel_count"]
        write_csv(schema_csv, class_rows, fieldnames)
        write_json(schema_json, {"schema_version": "HELIX_CLASS_SCHEMA_V1", "classes": class_rows})

        report = {
            "module": "spatial_reconstruction",
            "reference_grid": ref_path,
            "design_note": "Default output is a single-band hard class-ID raster. Multi-band class/source/probability stacks are optional.",
            "class_mapping": "Vector string values and schema-defined raster source values are mapped to integer class IDs and stored in the schema CSV/JSON.",
            "method": self.METHOD_OPTIONS[method], "fusion_rule": self.FUSION_OPTIONS[fusion_rule], "resampling": self.RESAMPLING_OPTIONS[resampling_idx],
            "minimum_coverage": min_coverage, "source_count": len(created_sources),
            "source_nodata_value": nodata, "final_background_value": background_class,
            "supersampling_factor_requested": supersample, "supersampling_applied": False,
            "schema_raster_value_remapping": remap_events,
            "sources": source_meta if keep_intermediate else [{k: v for k, v in s.items() if k not in ("path", "mapped_vector")} for s in source_meta],
            "class_ids": class_ids, "class_schema_csv": schema_csv, "class_schema_json": schema_json,
            "outputs": {"hard_label": hard_path, "class_stack_optional": class_stack_path, "class_support_probabilities_optional": prob_path, "coverage_optional": coverage_path, "source_agreement_optional": agreement_path, "source_label_stack_optional": source_stack_path, "purity_optional": purity_path},
        }
        json_path = os.path.join(out_dir, "helix_spatial_report.json")
        write_json(json_path, report)
        write_html(os.path.join(out_dir, "helix_spatial_report.html"), "HELIX Spatial Reconstruction", [("What this module wrote", "<p>Default output is the EO-grid hard class-ID raster plus report/schema. Optional multi-band stacks are only written when selected.</p>"), ("Summary", f"<pre>{report}</pre>")])

        if not keep_intermediate:
            for p in created_sources:
                try: os.remove(p)
                except Exception: pass
            # keep mapped gpkg? remove too
            for s in source_meta:
                for k in ("mapped_vector",):
                    try:
                        mp = s.get(k)
                        if mp and os.path.exists(mp):
                            ogr.GetDriverByName("GPKG").DeleteDataSource(mp)
                    except Exception:
                        pass
            try: os.rmdir(tmp_dir)
            except Exception: pass

        if load_outputs:
            add_raster_to_project(hard_path, "HELIX spatial hard labels")
            if class_stack_path: add_raster_to_project(class_stack_path, "HELIX one-hot class stack")
            if prob_path: add_raster_to_project(prob_path, "HELIX spatial probabilities")
            if coverage_path: add_raster_to_project(coverage_path, "HELIX spatial coverage")
            if agreement_path: add_raster_to_project(agreement_path, "HELIX spatial source agreement")
            if source_stack_path: add_raster_to_project(source_stack_path, "HELIX spatial source labels")
            if purity_path: add_raster_to_project(purity_path, "HELIX spatial purity")

        return {self.OUT_FOLDER: out_dir, self.HARD_LABEL: hard_path, self.PROB_STACK: prob_path, self.CLASS_STACK: class_stack_path, self.COVERAGE: coverage_path, self.SOURCE_AGREEMENT: agreement_path, self.SOURCE_LABEL_STACK: source_stack_path, self.PURITY: purity_path, self.CLASS_SCHEMA: schema_csv, self.CLASS_SCHEMA_JSON: schema_json, self.REPORT_JSON: json_path}
