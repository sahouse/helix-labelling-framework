# -*- coding: utf-8 -*-
# Copyright (C) 2026 Sarah Hauser, Karlsruhe Institute of Technology (KIT)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import re

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

from ._utils import (
    resolve_output_folder,
    write_html,
    write_json,
    add_raster_to_project,
    make_advanced,
    load_class_ids,
    read_class_schema,
    band_description,
)


class ContextFeaturesAlgorithm(QgsProcessingAlgorithm):
    LABEL_RASTER = "LABEL_RASTER"
    PROBABILITY_STACK = "PROBABILITY_STACK"
    CLASS_IDS = "CLASS_IDS"
    CLASS_SCHEMA_CSV = "CLASS_SCHEMA_CSV"
    FEATURE_SET = "FEATURE_SET"
    RADIUS = "RADIUS"
    MULTI_RADII = "MULTI_RADII"
    WINDOW_SHAPE = "WINDOW_SHAPE"
    NODATA = "NODATA"
    WRITE_CLASS_CONTEXT = "WRITE_CLASS_CONTEXT"
    WRITE_LOCAL_PURITY = "WRITE_LOCAL_PURITY"
    WRITE_PAIRWISE_CONTEXT = "WRITE_PAIRWISE_CONTEXT"
    INCLUDE_SELF_PAIRS = "INCLUDE_SELF_PAIRS"
    MAX_PAIRWISE_BANDS = "MAX_PAIRWISE_BANDS"
    LOAD_OUTPUTS = "LOAD_OUTPUTS"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    OUT_FOLDER = "OUT_FOLDER"
    EDGE_RISK = "EDGE_RISK"
    DIVERSITY = "DIVERSITY"
    ENTROPY = "ENTROPY"
    MARGIN = "MARGIN"
    CLASS_SUPPORT = "CLASS_SUPPORT"
    LOCAL_PURITY = "LOCAL_PURITY"
    PAIRWISE_CONTEXT = "PAIRWISE_CONTEXT"
    REPORT_JSON = "REPORT_JSON"

    FEATURE_OPTIONS = [
        "Edge risk",
        "Neighbourhood diversity",
        "Probability entropy",
        "Probability margin top1-top2",
    ]
    WINDOW_OPTIONS = ["Square window", "Circular/disk window"]

    def name(self):
        return "context_features"

    def displayName(self):
        return "Context & risk features"

    def group(self):
        return "5 Context"

    def groupId(self):
        return "05_context"

    def shortHelpString(self):
        return (
            "Creates spatial/context features from hard labels and/or class/probability stacks: boundary risk, local diversity, "
            "entropy, probability margin, local purity, multi-radius per-class neighbourhood support, and optional class-pair "
            "interaction features such as class A near class B. These outputs are separate from Spatial Reconstruction and can be "
            "used as ML features or passed into Soft Targets & Weights."
        )

    def createInstance(self):
        return ContextFeaturesAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.LABEL_RASTER, "Hard label raster (single-band class IDs)", optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer(self.PROBABILITY_STACK, "Class support/probability/soft-target stack", optional=True))
        self.addParameter(QgsProcessingParameterString(self.CLASS_IDS, "Class IDs for hard-label per-class context; empty = infer", defaultValue="", optional=True))
        self.addParameter(make_advanced(QgsProcessingParameterFile(self.CLASS_SCHEMA_CSV, "Optional class schema CSV", behavior=QgsProcessingParameterFile.File, extension="csv", optional=True)))
        self.addParameter(QgsProcessingParameterEnum(self.FEATURE_SET, "Global features to calculate", self.FEATURE_OPTIONS, allowMultiple=True, defaultValue=[0, 1, 2, 3]))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.RADIUS, "main neighbourhood radius [pixels]", type=QgsProcessingParameterNumber.Integer, minValue=1, maxValue=250, defaultValue=2)))
        self.addParameter(make_advanced(QgsProcessingParameterString(self.MULTI_RADII, "additional/multi radii [pixels], e.g. 2,5,10; empty = main radius", defaultValue="", optional=True)))
        self.addParameter(make_advanced(QgsProcessingParameterEnum(self.WINDOW_SHAPE, "neighbourhood window shape", self.WINDOW_OPTIONS, defaultValue=0)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.NODATA, "NoData/background value", type=QgsProcessingParameterNumber.Integer, defaultValue=0)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_CLASS_CONTEXT, "write multi-radius per-class neighbourhood support stack", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_LOCAL_PURITY, "write local purity/dominance stack", defaultValue=True)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.WRITE_PAIRWISE_CONTEXT, "write class-pair context stack (class A near class B)", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.INCLUDE_SELF_PAIRS, "include self-pairs in class-pair stack", defaultValue=False)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.MAX_PAIRWISE_BANDS, "maximum class-pair bands to write", type=QgsProcessingParameterNumber.Integer, minValue=1, maxValue=5000, defaultValue=300)))
        self.addParameter(make_advanced(QgsProcessingParameterBoolean(self.LOAD_OUTPUTS, "load outputs into QGIS", defaultValue=True)))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT_FOLDER, "Output folder"))
        self.addOutput(QgsProcessingOutputFolder(self.OUT_FOLDER, "Output folder"))
        self.addOutput(QgsProcessingOutputFile(self.EDGE_RISK, "Edge-risk raster"))
        self.addOutput(QgsProcessingOutputFile(self.DIVERSITY, "Neighbourhood diversity raster"))
        self.addOutput(QgsProcessingOutputFile(self.ENTROPY, "Probability entropy raster"))
        self.addOutput(QgsProcessingOutputFile(self.MARGIN, "Probability margin raster"))
        self.addOutput(QgsProcessingOutputFile(self.CLASS_SUPPORT, "Optional multi-radius per-class neighbourhood support stack"))
        self.addOutput(QgsProcessingOutputFile(self.LOCAL_PURITY, "Optional local purity/dominance stack"))
        self.addOutput(QgsProcessingOutputFile(self.PAIRWISE_CONTEXT, "Optional class-pair context stack"))
        self.addOutput(QgsProcessingOutputFile(self.REPORT_JSON, "Report JSON"))

    @staticmethod
    def _parse_radii(text, fallback):
        radii = []
        for token in re.split(r"[,;\s]+", text or ""):
            if not token:
                continue
            try:
                r = int(float(token))
                if r > 0:
                    radii.append(r)
            except Exception:
                pass
        if not radii:
            radii = [int(fallback)]
        return sorted(dict.fromkeys(radii))

    def processAlgorithm(self, parameters, context, feedback):
        try:
            from osgeo import gdal
            import numpy as np
        except Exception as e:
            raise QgsProcessingException(f"HELIX context features need GDAL and NumPy. Import failed: {e}")

        out_dir = resolve_output_folder(self, parameters, self.OUTPUT_FOLDER, context, "helix_context")
        label_layer = self.parameterAsRasterLayer(parameters, self.LABEL_RASTER, context)
        prob_layer = self.parameterAsRasterLayer(parameters, self.PROBABILITY_STACK, context)
        selected = self.parameterAsEnums(parameters, self.FEATURE_SET, context)
        radius = max(1, self.parameterAsInt(parameters, self.RADIUS, context))
        radii = self._parse_radii(self.parameterAsString(parameters, self.MULTI_RADII, context) or "", radius)
        window_shape = self.parameterAsEnum(parameters, self.WINDOW_SHAPE, context)
        nodata = self.parameterAsInt(parameters, self.NODATA, context)
        class_ids_text = self.parameterAsString(parameters, self.CLASS_IDS, context) or ""
        schema = read_class_schema(self.parameterAsFile(parameters, self.CLASS_SCHEMA_CSV, context))
        class_names = schema.get("class_names", {})
        schema_class_ids = schema.get("class_ids", [])
        write_class_context = self.parameterAsBool(parameters, self.WRITE_CLASS_CONTEXT, context)
        write_local_purity = self.parameterAsBool(parameters, self.WRITE_LOCAL_PURITY, context)
        write_pairwise_context = self.parameterAsBool(parameters, self.WRITE_PAIRWISE_CONTEXT, context)
        include_self_pairs = self.parameterAsBool(parameters, self.INCLUDE_SELF_PAIRS, context)
        max_pairwise_bands = max(1, self.parameterAsInt(parameters, self.MAX_PAIRWISE_BANDS, context))
        load_outputs = self.parameterAsBool(parameters, self.LOAD_OUTPUTS, context)
        if label_layer is None and prob_layer is None:
            raise QgsProcessingException("Provide at least a hard label raster or a class/probability stack.")

        template_path = (label_layer or prob_layer).source().split("|", 1)[0]
        template = gdal.Open(template_path)
        if template is None:
            raise QgsProcessingException(f"Could not open template raster: {template_path}")
        gt, proj, xsize, ysize = template.GetGeoTransform(), template.GetProjection(), template.RasterXSize, template.RasterYSize

        def check_same_grid(ds, label):
            if ds is None:
                raise QgsProcessingException(f"Could not open {label}.")
            if ds.RasterXSize != xsize or ds.RasterYSize != ysize:
                raise QgsProcessingException(f"{label} must match the template raster grid/shape ({xsize} × {ysize}).")

        drv = gdal.GetDriverByName("GTiff")
        creation_opts = ["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"]

        def create(path, bands=1, dtype=gdal.GDT_Float32, nodata_value=0.0):
            ds = drv.Create(path, xsize, ysize, bands, dtype, creation_opts)
            ds.SetGeoTransform(gt)
            ds.SetProjection(proj)
            for bi in range(1, bands + 1):
                ds.GetRasterBand(bi).SetNoDataValue(nodata_value)
            return ds

        def shift_array(arr, dy, dx, fill):
            out = np.full(arr.shape, fill, dtype=arr.dtype)
            y_src0 = max(0, -dy)
            y_src1 = arr.shape[0] - max(0, dy)
            x_src0 = max(0, -dx)
            x_src1 = arr.shape[1] - max(0, dx)
            y_dst0 = max(0, dy)
            y_dst1 = y_dst0 + max(0, y_src1 - y_src0)
            x_dst0 = max(0, dx)
            x_dst1 = x_dst0 + max(0, x_src1 - x_src0)
            if y_src1 > y_src0 and x_src1 > x_src0:
                out[y_dst0:y_dst1, x_dst0:x_dst1] = arr[y_src0:y_src1, x_src0:x_src1]
            return out

        def box_mean2d(arr, r):
            arr = arr.astype("float32", copy=False)
            if r <= 0:
                return arr.astype("float32", copy=True)
            pad = int(r)
            win = 2 * pad + 1
            padded = np.pad(arr, ((pad, pad), (pad, pad)), mode="constant", constant_values=0)
            integ = padded.cumsum(axis=0).cumsum(axis=1)
            integ = np.pad(integ, ((1, 0), (1, 0)), mode="constant", constant_values=0)
            sums = integ[win:, win:] - integ[:-win, win:] - integ[win:, :-win] + integ[:-win, :-win]
            ones = np.ones(arr.shape, dtype="float32")
            padded_ones = np.pad(ones, ((pad, pad), (pad, pad)), mode="constant", constant_values=0)
            cint = padded_ones.cumsum(axis=0).cumsum(axis=1)
            cint = np.pad(cint, ((1, 0), (1, 0)), mode="constant", constant_values=0)
            counts = cint[win:, win:] - cint[:-win, win:] - cint[win:, :-win] + cint[:-win, :-win]
            return (sums / np.maximum(counts, 1.0)).astype("float32")

        def disk_offsets(r):
            rr = int(r)
            return [(dy, dx) for dy in range(-rr, rr + 1) for dx in range(-rr, rr + 1) if (dy * dy + dx * dx) <= rr * rr]

        def disk_mean2d(arr, r):
            arr = arr.astype("float32", copy=False)
            offsets = disk_offsets(r)
            out = np.zeros(arr.shape, dtype="float32")
            counts = np.zeros(arr.shape, dtype="float32")
            one = np.ones(arr.shape, dtype="uint8")
            for dy, dx in offsets:
                out += shift_array(arr, dy, dx, 0.0)
                counts += shift_array(one, dy, dx, 0).astype("float32")
            return (out / np.maximum(counts, 1.0)).astype("float32")

        def local_mean_stack(stack, r):
            # stack shape: [bands, y, x]. Mean in a square/disk window, no wrap-around at borders.
            out = np.zeros_like(stack, dtype="float32")
            for bi in range(stack.shape[0]):
                out[bi] = disk_mean2d(stack[bi], r) if window_shape == 1 else box_mean2d(stack[bi], r)
            return out

        def normalise_class_stack(stack):
            s = stack.sum(axis=0, keepdims=True)
            return np.where(s > 0, stack / np.maximum(s, 1e-12), 0.0).astype("float32")

        outputs = {
            "edge_risk": "",
            "diversity": "",
            "entropy": "",
            "margin": "",
            "class_support": "",
            "local_purity": "",
            "pairwise_context": "",
        }

        label = None
        class_ids = []
        if label_layer is not None:
            ds = gdal.Open(label_layer.source().split("|", 1)[0])
            check_same_grid(ds, "Hard label raster")
            label = ds.GetRasterBand(1).ReadAsArray()
            ds = None
            class_ids = load_class_ids(class_ids_text, arrays=None, nodata=nodata) or list(schema_class_ids) or load_class_ids("", arrays=[label], nodata=nodata)

        p = None
        if prob_layer is not None:
            ds = gdal.Open(prob_layer.source().split("|", 1)[0])
            check_same_grid(ds, "Probability stack")
            p = np.stack([ds.GetRasterBand(bi).ReadAsArray().astype("float32") for bi in range(1, ds.RasterCount + 1)], axis=0)
            ds = None
            p = normalise_class_stack(p)
            if not class_ids:
                class_ids = load_class_ids(class_ids_text, arrays=None, nodata=nodata) or list(schema_class_ids) or list(range(1, p.shape[0] + 1))
            if len(class_ids) != p.shape[0]:
                raise QgsProcessingException(f"Class ID count ({len(class_ids)}) must match probability stack band count ({p.shape[0]}).")

        if label is not None and (0 in selected or 1 in selected):
            valid = label != nodata
            edge = np.zeros(label.shape, dtype=bool)
            edge[:, 1:] |= (label[:, 1:] != label[:, :-1]) & valid[:, 1:] & valid[:, :-1]
            edge[1:, :] |= (label[1:, :] != label[:-1, :]) & valid[1:, :] & valid[:-1, :]
            dil = edge.copy()
            for _ in range(radius):
                dil |= (
                    shift_array(dil.astype("uint8"), 1, 0, 0).astype(bool)
                    | shift_array(dil.astype("uint8"), -1, 0, 0).astype(bool)
                    | shift_array(dil.astype("uint8"), 0, 1, 0).astype(bool)
                    | shift_array(dil.astype("uint8"), 0, -1, 0).astype(bool)
                )
            if 0 in selected:
                out = os.path.join(out_dir, "helix_context_edge_risk.tif")
                ds = create(out, 1, gdal.GDT_Byte, 0)
                b = ds.GetRasterBand(1)
                b.SetDescription(f"edge_risk_0_100_R{radius}")
                b.WriteArray((dil.astype("uint8") * 100))
                ds.FlushCache()
                ds = None
                outputs["edge_risk"] = out
            if 1 in selected:
                changes = np.zeros(label.shape, dtype="float32")
                valid_neighbour_count = np.zeros(label.shape, dtype="float32")
                offsets = disk_offsets(radius) if window_shape == 1 else [(dy, dx) for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)]
                for dy, dx in offsets:
                    if dx == 0 and dy == 0:
                        continue
                    sh = shift_array(label, dy, dx, nodata)
                    sv = shift_array(valid.astype("uint8"), dy, dx, 0).astype(bool)
                    pair_valid = valid & sv
                    changes += ((sh != label) & pair_valid).astype("float32")
                    valid_neighbour_count += pair_valid.astype("float32")
                div = np.where(valid & (valid_neighbour_count > 0), changes / np.maximum(valid_neighbour_count, 1.0), 0.0)
                out = os.path.join(out_dir, "helix_context_diversity.tif")
                ds = create(out)
                b = ds.GetRasterBand(1)
                b.SetDescription(f"neighbourhood_class_diversity_R{radius}")
                b.WriteArray(div.astype("float32"))
                ds.FlushCache()
                ds = None
                outputs["diversity"] = out

        if p is not None and (2 in selected or 3 in selected):
            if 2 in selected:
                ent = -(p * np.log(np.maximum(p, 1e-12))).sum(axis=0) / max(np.log(p.shape[0]), 1e-12)
                out = os.path.join(out_dir, "helix_context_entropy.tif")
                ds = create(out)
                b = ds.GetRasterBand(1)
                b.SetDescription("class_probability_entropy")
                b.WriteArray(ent.astype("float32"))
                ds.FlushCache()
                ds = None
                outputs["entropy"] = out
            if 3 in selected:
                if p.shape[0] >= 2:
                    part = np.partition(p, -2, axis=0)
                    margin = part[-1, :, :] - part[-2, :, :]
                else:
                    margin = p[0]
                out = os.path.join(out_dir, "helix_context_margin.tif")
                ds = create(out)
                b = ds.GetRasterBand(1)
                b.SetDescription("top1_minus_top2_probability_margin")
                b.WriteArray(margin.astype("float32"))
                ds.FlushCache()
                ds = None
                outputs["margin"] = out

        base = None
        if write_class_context or write_local_purity or write_pairwise_context:
            if p is not None:
                base = p
            elif label is not None:
                if not class_ids:
                    class_ids = load_class_ids("", arrays=[label], nodata=nodata)
                base = np.zeros((len(class_ids), ysize, xsize), dtype="float32")
                for i, cid in enumerate(class_ids):
                    base[i] = (label == int(cid)).astype("float32")
            if base is not None and base.shape[0] > 0:
                base = normalise_class_stack(base)

        support_by_radius = {}
        if base is not None and (write_class_context or write_local_purity or write_pairwise_context):
            for r in radii:
                support_by_radius[r] = normalise_class_stack(local_mean_stack(base, r))

        if support_by_radius and write_class_context:
            band_count = len(class_ids) * len(radii)
            out = os.path.join(out_dir, "helix_context_class_support_multiradius.tif")
            ds = create(out, band_count, gdal.GDT_Float32, 0)
            bi = 1
            for r in radii:
                class_support = support_by_radius[r]
                for ci, cid in enumerate(class_ids):
                    b = ds.GetRasterBand(bi)
                    b.SetDescription(band_description(cid, class_names, f"local_support_R{r}")[:120])
                    b.WriteArray(class_support[ci])
                    bi += 1
            ds.FlushCache()
            ds = None
            outputs["class_support"] = out

        if support_by_radius and write_local_purity:
            out = os.path.join(out_dir, "helix_context_local_purity_multiradius.tif")
            ds = create(out, len(radii), gdal.GDT_Float32, 0)
            for bi, r in enumerate(radii, 1):
                purity = support_by_radius[r].max(axis=0).astype("float32")
                b = ds.GetRasterBand(bi)
                b.SetDescription(f"local_top_class_support_purity_R{r}")
                b.WriteArray(purity)
            ds.FlushCache()
            ds = None
            outputs["local_purity"] = out

        pair_count_written = 0
        pair_count_possible = 0
        if support_by_radius and write_pairwise_context:
            pair_defs = []
            for r in radii:
                for ci, cid_i in enumerate(class_ids):
                    for cj, cid_j in enumerate(class_ids):
                        if (not include_self_pairs) and int(cid_i) == int(cid_j):
                            continue
                        pair_count_possible += 1
                        if len(pair_defs) < max_pairwise_bands:
                            pair_defs.append((r, ci, cid_i, cj, cid_j))
            if pair_defs:
                out = os.path.join(out_dir, "helix_context_class_pair_context.tif")
                ds = create(out, len(pair_defs), gdal.GDT_Float32, 0)
                for bi, (r, ci, cid_i, cj, cid_j) in enumerate(pair_defs, 1):
                    # Soft ordered interaction: probability/support of focal class i at the centre times
                    # local neighbourhood support of class j. For hard labels this becomes "class i pixel near class j".
                    arr = (base[ci] * support_by_radius[r][cj]).astype("float32")
                    b = ds.GetRasterBand(bi)
                    desc_i = band_description(cid_i, class_names, "")
                    desc_j = band_description(cid_j, class_names, "")
                    b.SetDescription(f"{desc_i}_near_{desc_j}_R{r}"[:120])
                    b.WriteArray(arr)
                    pair_count_written += 1
                ds.FlushCache()
                ds = None
                outputs["pairwise_context"] = out

        if load_outputs:
            for key, path in outputs.items():
                if path:
                    add_raster_to_project(path, "HELIX " + key.replace("_", " "))

        json_path = os.path.join(out_dir, "helix_context_report.json")
        report = {
            "module": "context_features",
            "selected_features": [self.FEATURE_OPTIONS[i] for i in selected],
            "main_radius_pixels": radius,
            "multi_radii_pixels": radii,
            "window_shape": self.WINDOW_OPTIONS[window_shape] if 0 <= window_shape < len(self.WINDOW_OPTIONS) else str(window_shape),
            "class_ids": class_ids,
            "class_schema_used": bool(schema.get("rows")),
            "per_class_context_written": bool(outputs["class_support"]),
            "local_purity_written": bool(outputs["local_purity"]),
            "pairwise_context_written": bool(outputs["pairwise_context"]),
            "pairwise_possible_bands": pair_count_possible,
            "pairwise_written_bands": pair_count_written,
            "outputs": outputs,
            "notes": [
                "Global context outputs are one-band rasters using the main radius.",
                "Class-support output is one band per class and radius: class_c_local_support_Rr.",
                "Local purity output is one band per radius and stores max local class support.",
                "Pairwise context is ordered and stores centre support of class A times neighbourhood support of class B.",
                "No wrap-around is used at raster borders.",
            ],
        }
        if pair_count_possible > pair_count_written:
            report["notes"].append("Pairwise output was truncated by the maximum class-pair band limit.")
        write_json(json_path, report)
        write_html(os.path.join(out_dir, "helix_context_report.html"), "HELIX Context & Risk Features", [("Summary", f"<pre>{report}</pre>")])
        return {
            self.OUT_FOLDER: out_dir,
            self.EDGE_RISK: outputs["edge_risk"],
            self.DIVERSITY: outputs["diversity"],
            self.ENTROPY: outputs["entropy"],
            self.MARGIN: outputs["margin"],
            self.CLASS_SUPPORT: outputs["class_support"],
            self.LOCAL_PURITY: outputs["local_purity"],
            self.PAIRWISE_CONTEXT: outputs["pairwise_context"],
            self.REPORT_JSON: json_path,
        }
