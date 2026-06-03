# -*- coding: utf-8 -*-
# Copyright (C) 2026 Sarah Hauser, Karlsruhe Institute of Technology (KIT)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import csv
import os

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterFile,
)

from ._utils import resolve_output_folder, load_class_ids, add_raster_to_project, write_html, write_json, make_advanced, read_class_schema, band_description


class SoftSupervisionAlgorithm(QgsProcessingAlgorithm):
    HARD_LABEL = "HARD_LABEL"
    PROBABILITY_STACK = "PROBABILITY_STACK"
    EDGE_RISK = "EDGE_RISK"
    CLASS_CONTEXT_STACK = "CLASS_CONTEXT_STACK"
    SOURCE_AGREEMENT = "SOURCE_AGREEMENT"
    TEMPORAL_QUALITY = "TEMPORAL_QUALITY"
    TEMPORAL_MATCH_CSV = "TEMPORAL_MATCH_CSV"
    CLASS_IDS = "CLASS_IDS"
    CLASS_SCHEMA_CSV = "CLASS_SCHEMA_CSV"
    HARD_INPUT_MODE = "HARD_INPUT_MODE"
    MODE = "MODE"
    ALPHA_BASE = "ALPHA_BASE"
    ALPHA_MAX = "ALPHA_MAX"
    BETA_EDGE = "BETA_EDGE"
    BETA_TEMPORAL = "BETA_TEMPORAL"
    BETA_SOURCE = "BETA_SOURCE"
    BETA_CONTEXT = "BETA_CONTEXT"
    QUALITY_PRIOR = "QUALITY_PRIOR"
    CLASS_BALANCE = "CLASS_BALANCE"
    WRITE_CLASS_CONFIDENCE = "WRITE_CLASS_CONFIDENCE"
    WRITE_CLASS_UNCERTAINTY = "WRITE_CLASS_UNCERTAINTY"
    WRITE_CLASS_WEIGHTS = "WRITE_CLASS_WEIGHTS"
    NODATA = "NODATA"
    LOAD_OUTPUTS = "LOAD_OUTPUTS"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    OUT_FOLDER = "OUT_FOLDER"
    SOFT_TARGETS = "SOFT_TARGETS"
    UNCERTAINTY = "UNCERTAINTY"
    WEIGHTS = "WEIGHTS"
    CLASS_CONFIDENCE = "CLASS_CONFIDENCE"
    CLASS_UNCERTAINTY = "CLASS_UNCERTAINTY"
    CLASS_WEIGHTS = "CLASS_WEIGHTS"
    REPORT_JSON = "REPORT_JSON"

    HARD_INPUT_MODE_OPTIONS = ["Single-band class-ID raster", "Multi-band one-hot / hard class stack"]
    MODE_OPTIONS = ["Hard labels → soft targets", "Probability stack → calibrated UST", "Hard + probabilities + context risk"]
    BALANCE_OPTIONS = ["No class balancing", "Inverse frequency", "Sqrt inverse frequency"]

    def name(self):
        return "soft_supervision"

    def displayName(self):
        return "Soft targets & weights (UST)"

    def group(self):
        return "6 Soft supervision"

    def groupId(self):
        return "06_supervision"

    def shortHelpString(self):
        return (
            "Creates uncertainty-aware supervision targets (UST): soft probability targets, uncertainty and training weights. "
            "Can start from hard labels or an existing probability stack, and can incorporate edge risk and temporal quality."
        )

    def createInstance(self):
        return SoftSupervisionAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.HARD_LABEL, "Hard label raster", optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(self.PROBABILITY_STACK, "Probability stack", optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(self.EDGE_RISK, "Optional edge-risk raster", optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(self.CLASS_CONTEXT_STACK, "Optional per-class context/support stack", optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(self.SOURCE_AGREEMENT, "Optional source-agreement / purity raster", optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(self.TEMPORAL_QUALITY, "Optional temporal-quality raster", optional=True))
        self.addParameter(make_advanced(QgsProcessingParameterFile(self.TEMPORAL_MATCH_CSV, "Optional temporal match CSV from Temporal Reconciliation", behavior=QgsProcessingParameterFile.File, extension="csv", optional=True)))
        self.addParameter(QgsProcessingParameterString(self.CLASS_IDS, "Class IDs, comma-separated; empty = infer", defaultValue="", optional=True))
        self.addParameter(make_advanced(QgsProcessingParameterFile(self.CLASS_SCHEMA_CSV, "Optional class schema CSV", behavior=QgsProcessingParameterFile.File, extension="csv", optional=True)))
        self.addParameter(make_advanced(QgsProcessingParameterEnum(self.HARD_INPUT_MODE, "hard-label input interpretation", self.HARD_INPUT_MODE_OPTIONS, defaultValue=0)))
        self.addParameter(make_advanced(QgsProcessingParameterEnum(self.MODE, "UST mode", self.MODE_OPTIONS, defaultValue=0)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.ALPHA_BASE, "base label smoothing alpha", type=QgsProcessingParameterNumber.Double, minValue=0.0, maxValue=1.0, defaultValue=0.03)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.ALPHA_MAX, "maximum smoothing/uncertainty alpha", type=QgsProcessingParameterNumber.Double, minValue=0.0, maxValue=1.0, defaultValue=0.35)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.BETA_EDGE, "edge-risk contribution", type=QgsProcessingParameterNumber.Double, minValue=0.0, maxValue=5.0, defaultValue=0.25)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.BETA_TEMPORAL, "stale/temporal-risk contribution", type=QgsProcessingParameterNumber.Double, minValue=0.0, maxValue=5.0, defaultValue=0.25)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.BETA_SOURCE, "source-disagreement contribution", type=QgsProcessingParameterNumber.Double, minValue=0.0, maxValue=5.0, defaultValue=0.25)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.BETA_CONTEXT, "class-context ambiguity contribution", type=QgsProcessingParameterNumber.Double, minValue=0.0, maxValue=5.0, defaultValue=0.25)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.QUALITY_PRIOR, "global quality prior Q [0..1]", type=QgsProcessingParameterNumber.Double, minValue=0.0, maxValue=1.0, defaultValue=0.85)))
        self.addParameter(make_advanced(QgsProcessingParameterEnum(self.CLASS_BALANCE, "class balancing for weights", self.BALANCE_OPTIONS, defaultValue=0)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_CLASS_CONFIDENCE, "write per-class confidence stack", defaultValue=True)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_CLASS_UNCERTAINTY, "write per-class uncertainty stack", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_CLASS_WEIGHTS, "write per-class weight stack", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.NODATA, "NoData/background value", type=QgsProcessingParameterNumber.Integer, defaultValue=0)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.LOAD_OUTPUTS, "load outputs into QGIS", defaultValue=True)))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT_FOLDER, "Output folder"))
        self.addOutput(QgsProcessingOutputFolder(self.OUT_FOLDER, "Output folder"))
        self.addOutput(QgsProcessingOutputFile(self.SOFT_TARGETS, "Soft target stack"))
        self.addOutput(QgsProcessingOutputFile(self.UNCERTAINTY, "Uncertainty raster"))
        self.addOutput(QgsProcessingOutputFile(self.WEIGHTS, "Training weights raster"))
        self.addOutput(QgsProcessingOutputFile(self.CLASS_CONFIDENCE, "Optional per-class confidence stack"))
        self.addOutput(QgsProcessingOutputFile(self.CLASS_UNCERTAINTY, "Optional per-class uncertainty stack"))
        self.addOutput(QgsProcessingOutputFile(self.CLASS_WEIGHTS, "Optional per-class weights stack"))
        self.addOutput(QgsProcessingOutputFile(self.REPORT_JSON, "Report JSON"))

    def processAlgorithm(self, parameters, context, feedback):
        try:
            from osgeo import gdal
            import numpy as np
        except Exception as e:
            raise QgsProcessingException(f"HELIX soft supervision needs GDAL and NumPy. Import failed: {e}")

        out_dir = resolve_output_folder(self, parameters, self.OUTPUT_FOLDER, context, "helix_ust")
        hard_layer = self.parameterAsRasterLayer(parameters, self.HARD_LABEL, context)
        prob_layer = self.parameterAsRasterLayer(parameters, self.PROBABILITY_STACK, context)
        edge_layer = self.parameterAsRasterLayer(parameters, self.EDGE_RISK, context)
        temporal_layer = self.parameterAsRasterLayer(parameters, self.TEMPORAL_QUALITY, context)
        temporal_match_csv = self.parameterAsFile(parameters, self.TEMPORAL_MATCH_CSV, context)
        context_stack_layer = self.parameterAsRasterLayer(parameters, self.CLASS_CONTEXT_STACK, context)
        source_agreement_layer = self.parameterAsRasterLayer(parameters, self.SOURCE_AGREEMENT, context)
        if hard_layer is None and prob_layer is None:
            raise QgsProcessingException("Provide either a hard label raster or a probability stack.")

        hard_input_mode = self.parameterAsEnum(parameters, self.HARD_INPUT_MODE, context)
        mode = self.parameterAsEnum(parameters, self.MODE, context)
        alpha_base = float(self.parameterAsDouble(parameters, self.ALPHA_BASE, context))
        alpha_max = float(self.parameterAsDouble(parameters, self.ALPHA_MAX, context))
        beta_edge = float(self.parameterAsDouble(parameters, self.BETA_EDGE, context))
        beta_temporal = float(self.parameterAsDouble(parameters, self.BETA_TEMPORAL, context))
        beta_source = float(self.parameterAsDouble(parameters, self.BETA_SOURCE, context))
        beta_context = float(self.parameterAsDouble(parameters, self.BETA_CONTEXT, context))
        q = float(self.parameterAsDouble(parameters, self.QUALITY_PRIOR, context))
        balance = self.parameterAsEnum(parameters, self.CLASS_BALANCE, context)
        write_class_confidence = self.parameterAsBool(parameters, self.WRITE_CLASS_CONFIDENCE, context)
        write_class_uncertainty = self.parameterAsBool(parameters, self.WRITE_CLASS_UNCERTAINTY, context)
        write_class_weights = self.parameterAsBool(parameters, self.WRITE_CLASS_WEIGHTS, context)
        nodata = self.parameterAsInt(parameters, self.NODATA, context)
        load_outputs = self.parameterAsBool(parameters, self.LOAD_OUTPUTS, context)

        template_layer = prob_layer or hard_layer
        template = gdal.Open(template_layer.source().split("|", 1)[0])
        if template is None:
            raise QgsProcessingException("Could not open template raster.")
        gt, proj, xsize, ysize = template.GetGeoTransform(), template.GetProjection(), template.RasterXSize, template.RasterYSize

        def check_same_grid(ds, label):
            if ds is None:
                raise QgsProcessingException(f"Could not open {label}.")
            if ds.RasterXSize != xsize or ds.RasterYSize != ysize:
                raise QgsProcessingException(f"{label} must match the template raster grid/shape ({xsize} × {ysize}).")

        class_ids_text = self.parameterAsString(parameters, self.CLASS_IDS, context) or ""
        schema = read_class_schema(self.parameterAsFile(parameters, self.CLASS_SCHEMA_CSV, context))
        class_names = schema.get("class_names", {})
        schema_class_ids = schema.get("class_ids", [])
        class_ids = load_class_ids(class_ids_text, arrays=None, nodata=nodata) or list(schema_class_ids)
        hard = None
        hard_multiband = None
        valid = None
        source_mode_used = ""

        if prob_layer is not None and mode in (1, 2):
            ds = gdal.Open(prob_layer.source().split("|", 1)[0])
            check_same_grid(ds, "Probability stack")
            probs = [ds.GetRasterBand(bi).ReadAsArray().astype("float32") for bi in range(1, ds.RasterCount + 1)]
            ds = None
            p = np.stack(probs, axis=0)
            if not class_ids:
                class_ids = list(schema_class_ids) or list(range(1, p.shape[0] + 1))
            if len(class_ids) != p.shape[0]:
                raise QgsProcessingException(
                    f"Class ID count ({len(class_ids)}) must match probability stack band count ({p.shape[0]})."
                )
            s = p.sum(axis=0, keepdims=True)
            p = np.where(s > 0, p / np.maximum(s, 1e-12), 0.0).astype("float32")
            valid = s[0] > 0
            source_mode_used = "probability_stack"
        else:
            if hard_layer is None:
                raise QgsProcessingException("Hard-label mode requires a hard label raster.")
            ds = gdal.Open(hard_layer.source().split("|", 1)[0])
            if ds is None:
                raise QgsProcessingException("Could not open hard label raster.")
            check_same_grid(ds, "Hard label raster")
            # Single-band class-ID raster: values are class IDs.
            if hard_input_mode == 0 or ds.RasterCount == 1:
                hard = ds.GetRasterBand(1).ReadAsArray().astype("int32")
                ds = None
                if not class_ids:
                    class_ids = load_class_ids("", arrays=[hard], nodata=nodata)
                if not class_ids:
                    raise QgsProcessingException("No class IDs found/inferred from hard label raster.")
                valid = hard != nodata
                p = np.zeros((len(class_ids), ysize, xsize), dtype="float32")
                for i, cid in enumerate(class_ids):
                    p[i] = (hard == cid).astype("float32")
                source_mode_used = "single_band_class_ids"
            # Multi-band hard stack: each band is class membership/support/probability for one class.
            else:
                bands = [ds.GetRasterBand(bi).ReadAsArray().astype("float32") for bi in range(1, ds.RasterCount + 1)]
                ds = None
                p = np.stack(bands, axis=0)
                # Treat positive values as support and normalize; works for one-hot and class-support stacks.
                p = np.where(p == float(nodata), 0.0, p)
                p = np.clip(p, 0.0, None).astype("float32")
                if not class_ids:
                    class_ids = list(range(1, p.shape[0] + 1))
                if len(class_ids) != p.shape[0]:
                    raise QgsProcessingException(
                        f"Class ID count ({len(class_ids)}) must match hard stack band count ({p.shape[0]})."
                    )
                s = p.sum(axis=0, keepdims=True)
                valid = s[0] > 0
                p = np.where(s > 0, p / np.maximum(s, 1e-12), 0.0).astype("float32")
                hard_multiband = p.copy()
                hard = np.zeros((ysize, xsize), dtype="int32")
                if p.shape[0] > 0:
                    hard_idx = np.argmax(p, axis=0)
                    for i, cid in enumerate(class_ids):
                        hard[(hard_idx == i) & valid] = int(cid)
                source_mode_used = "multi_band_hard_stack"

        edge = np.zeros((ysize, xsize), dtype="float32")
        if edge_layer is not None:
            ds = gdal.Open(edge_layer.source().split("|", 1)[0])
            check_same_grid(ds, "Edge-risk raster")
            edge = ds.GetRasterBand(1).ReadAsArray().astype("float32"); ds = None
            edge = np.clip(edge / (100.0 if edge.max() > 1.0 else 1.0), 0, 1)
        temporal_risk = np.zeros((ysize, xsize), dtype="float32")
        temporal_quality_from_csv = None
        if temporal_layer is not None:
            ds = gdal.Open(temporal_layer.source().split("|", 1)[0])
            check_same_grid(ds, "Temporal-quality raster")
            tq = ds.GetRasterBand(1).ReadAsArray().astype("float32"); ds = None
            if tq.max() > 1.0:
                tq = tq / 100.0
            temporal_risk = 1.0 - np.clip(tq, 0, 1)
        elif temporal_match_csv:
            qualities = []
            try:
                with open(temporal_match_csv, newline="", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if str(row.get("accepted", "1")).strip() in ("0", "False", "false", "no"):
                            continue
                        val = row.get("temporal_quality", "")
                        if str(val).strip() != "":
                            qualities.append(float(val))
                if qualities:
                    temporal_quality_from_csv = max(0.0, min(1.0, sum(qualities) / float(len(qualities))))
                    temporal_risk[:, :] = 1.0 - temporal_quality_from_csv
            except Exception as e:
                raise QgsProcessingException(f"Could not read temporal match CSV: {e}")

        source_risk = np.zeros((ysize, xsize), dtype="float32")
        if source_agreement_layer is not None:
            ds = gdal.Open(source_agreement_layer.source().split("|", 1)[0])
            check_same_grid(ds, "Source-agreement raster")
            ag = ds.GetRasterBand(1).ReadAsArray().astype("float32"); ds = None
            if ag.max() > 1.0:
                ag = ag / 100.0
            source_risk = 1.0 - np.clip(ag, 0, 1)

        context_risk = np.zeros((ysize, xsize), dtype="float32")
        class_context = None
        if context_stack_layer is not None:
            ds = gdal.Open(context_stack_layer.source().split("|", 1)[0])
            check_same_grid(ds, "Class-context stack")
            if ds.RasterCount == p.shape[0]:
                class_context = np.stack([ds.GetRasterBand(bi).ReadAsArray().astype("float32") for bi in range(1, ds.RasterCount + 1)], axis=0)
                cs = class_context.sum(axis=0, keepdims=True)
                class_context = np.where(cs > 0, class_context / np.maximum(cs, 1e-12), 0.0).astype("float32")
                context_risk = (1.0 - class_context.max(axis=0)).astype("float32")
            else:
                raise QgsProcessingException(f"Class-context stack band count ({ds.RasterCount}) must match class count ({p.shape[0]}).")
            ds = None

        alpha = np.clip(alpha_base + beta_edge * edge + beta_temporal * temporal_risk + beta_source * source_risk + beta_context * context_risk, 0, alpha_max).astype("float32")
        c = max(p.shape[0], 1)
        class_quality = np.array([max(0.0, min(1.0, float(schema.get("quality_q", {}).get(int(cid), 1.0)))) for cid in class_ids], dtype="float32")
        if c > 1:
            p_soft = p * (1.0 - alpha[None, :, :]) + (alpha[None, :, :] / float(c))
        else:
            p_soft = p
        p_soft[:, ~valid] = 0.0
        s = p_soft.sum(axis=0, keepdims=True)
        p_soft = np.where(s > 0, p_soft / np.maximum(s, 1e-12), 0.0).astype("float32")

        maxp = p_soft.max(axis=0)
        entropy = -(p_soft * np.log(np.maximum(p_soft, 1e-12))).sum(axis=0) / max(np.log(c), 1e-12)
        uncertainty = np.where(valid, np.maximum(1.0 - maxp, entropy).astype("float32"), 0.0)
        pixel_quality = np.clip((p * class_quality[:, None, None]).sum(axis=0), 0.0, 1.0).astype("float32")
        effective_q = np.clip(q * pixel_quality, 0.0, 1.0).astype("float32")
        weights = np.where(valid, effective_q * (1.0 - uncertainty) * (1.0 - 0.5 * edge) * (1.0 - 0.5 * temporal_risk) * (1.0 - 0.5 * source_risk) * (1.0 - 0.5 * context_risk), 0.0).astype("float32")

        if hard is not None and balance != 0:
            factors = {}
            total = max(int(valid.sum()), 1)
            for cid in class_ids:
                n = max(int(((hard == cid) & valid).sum()), 1)
                inv = float(total) / float(n * len(class_ids))
                factors[cid] = inv if balance == 1 else inv ** 0.5
            for cid, fac in factors.items():
                weights[hard == cid] *= fac
            weights = np.clip(weights, 0.0, 10.0)

        class_confidence = (p_soft * class_quality[:, None, None]).astype("float32")
        class_uncertainty = np.where(valid[None, :, :], (1.0 - class_confidence).astype("float32"), 0.0)
        class_weights = (p_soft * weights[None, :, :] * class_quality[:, None, None]).astype("float32")

        drv = gdal.GetDriverByName("GTiff")
        creation_opts = ["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"]

        def write_stack(path, arr, descriptions, nodata_value=0.0):
            ds_out = drv.Create(path, xsize, ysize, arr.shape[0], gdal.GDT_Float32, creation_opts)
            ds_out.SetGeoTransform(gt); ds_out.SetProjection(proj)
            for bi, desc in enumerate(descriptions, 1):
                b = ds_out.GetRasterBand(bi)
                b.SetNoDataValue(nodata_value)
                b.SetDescription(str(desc))
                b.WriteArray(arr[bi - 1].astype("float32"))
            ds_out.FlushCache(); ds_out = None
            return path

        soft_path = os.path.join(out_dir, "helix_soft_targets.tif")
        write_stack(soft_path, p_soft, [band_description(cid, class_names, "soft") for cid in class_ids])

        unc_path = os.path.join(out_dir, "helix_uncertainty.tif")
        ds = drv.Create(unc_path, xsize, ysize, 1, gdal.GDT_Float32, creation_opts)
        ds.SetGeoTransform(gt); ds.SetProjection(proj); ds.GetRasterBand(1).SetNoDataValue(0); ds.GetRasterBand(1).SetDescription("overall_uncertainty"); ds.GetRasterBand(1).WriteArray(uncertainty); ds.FlushCache(); ds = None

        w_path = os.path.join(out_dir, "helix_training_weights.tif")
        ds = drv.Create(w_path, xsize, ysize, 1, gdal.GDT_Float32, creation_opts)
        ds.SetGeoTransform(gt); ds.SetProjection(proj); ds.GetRasterBand(1).SetNoDataValue(0); ds.GetRasterBand(1).SetDescription("overall_training_weight"); ds.GetRasterBand(1).WriteArray(weights); ds.FlushCache(); ds = None

        class_conf_path = ""
        class_unc_path = ""
        class_w_path = ""
        if write_class_confidence:
            class_conf_path = os.path.join(out_dir, "helix_class_confidence.tif")
            write_stack(class_conf_path, class_confidence, [band_description(cid, class_names, "confidence") for cid in class_ids])
        if write_class_uncertainty:
            class_unc_path = os.path.join(out_dir, "helix_class_uncertainty.tif")
            write_stack(class_unc_path, class_uncertainty, [band_description(cid, class_names, "uncertainty") for cid in class_ids])
        if write_class_weights:
            class_w_path = os.path.join(out_dir, "helix_class_weights.tif")
            write_stack(class_w_path, class_weights, [band_description(cid, class_names, "weight") for cid in class_ids])

        if load_outputs:
            add_raster_to_project(soft_path, "HELIX soft targets")
            add_raster_to_project(unc_path, "HELIX uncertainty")
            add_raster_to_project(w_path, "HELIX training weights")
            if class_conf_path:
                add_raster_to_project(class_conf_path, "HELIX class confidence")
            if class_unc_path:
                add_raster_to_project(class_unc_path, "HELIX class uncertainty")
            if class_w_path:
                add_raster_to_project(class_w_path, "HELIX class weights")

        report = {
            "module": "soft_supervision",
            "mode": self.MODE_OPTIONS[mode],
            "hard_input_mode": self.HARD_INPUT_MODE_OPTIONS[hard_input_mode],
            "source_mode_used": source_mode_used,
            "class_ids": class_ids,
            "class_band_count": int(len(class_ids)),
            "class_schema_used": bool(schema.get("rows")),
            "alpha_base": alpha_base,
            "alpha_max": alpha_max,
            "beta_edge": beta_edge,
            "beta_temporal": beta_temporal,
            "beta_source": beta_source,
            "beta_context": beta_context,
            "quality_prior_Q": q,
            "class_quality_q": {str(cid): float(class_quality[i]) for i, cid in enumerate(class_ids)},
            "temporal_match_csv_used": bool(temporal_match_csv),
            "temporal_quality_from_csv_mean": temporal_quality_from_csv,
            "source_agreement_used": bool(source_agreement_layer is not None),
            "class_context_used": bool(context_stack_layer is not None),
            "class_balance": self.BALANCE_OPTIONS[balance],
            "outputs": {
                "soft_targets": soft_path,
                "overall_uncertainty": unc_path,
                "overall_weights": w_path,
                "class_confidence": class_conf_path,
                "class_uncertainty": class_unc_path,
                "class_weights": class_w_path,
            },
            "notes": [
                "Soft targets are always one band per class.",
                "Overall uncertainty/weights are one band per pixel and remain the recommended default for most ML losses.",
                "Optional class confidence/uncertainty/weight stacks are written band-wise for advanced workflows.",
                "Class quality_q values from the schema reduce effective Q and per-class confidence/weights when provided.",
                "Class weights are computed as overall weight multiplied by the soft-target probability and class quality of each class.",
                "Optional source-agreement, temporal match CSV/raster and per-class context stacks can further increase smoothing and reduce weights where sources/time/context are ambiguous."
            ]
        }
        json_path = os.path.join(out_dir, "helix_ust_report.json")
        write_json(json_path, report)
        write_html(os.path.join(out_dir, "helix_ust_report.html"), "HELIX Soft Targets & Weights", [("Summary", f"<pre>{report}</pre>")])
        result = {self.OUT_FOLDER: out_dir, self.SOFT_TARGETS: soft_path, self.UNCERTAINTY: unc_path, self.WEIGHTS: w_path, self.REPORT_JSON: json_path}
        if class_conf_path:
            result[self.CLASS_CONFIDENCE] = class_conf_path
        if class_unc_path:
            result[self.CLASS_UNCERTAINTY] = class_unc_path
        if class_w_path:
            result[self.CLASS_WEIGHTS] = class_w_path
        return result
