# -*- coding: utf-8 -*-
# Copyright (C) 2026 Sarah Hauser, Karlsruhe Institute of Technology (KIT)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import csv
import os
from datetime import date

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingParameterFolderDestination,
    QgsProcessing,
)

from ._utils import (
    parse_date_value, parse_dates_text, parse_dates_csv, dates_from_folder, date_to_iso,
    resolve_output_folder, write_csv, write_html, write_json, make_advanced, safe_feedback
)


class TemporalReconciliationAlgorithm(QgsProcessingAlgorithm):
    EO_DATES_TEXT = "EO_DATES_TEXT"
    EO_DATES_CSV = "EO_DATES_CSV"
    EO_DATE_FIELD = "EO_DATE_FIELD"
    EO_RASTER_FOLDER = "EO_RASTER_FOLDER"
    LABEL_TABLE_CSV = "LABEL_TABLE_CSV"
    LABEL_DATE_FIELD = "LABEL_DATE_FIELD"
    VALID_FROM_FIELD = "VALID_FROM_FIELD"
    VALID_TO_FIELD = "VALID_TO_FIELD"
    LABEL_ID_FIELD = "LABEL_ID_FIELD"
    METHOD = "METHOD"
    TOLERANCE_DAYS = "TOLERANCE_DAYS"
    BACKTRACK_DAYS = "BACKTRACK_DAYS"
    DECAY_HALFLIFE_DAYS = "DECAY_HALFLIFE_DAYS"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    OUT_FOLDER = "OUT_FOLDER"
    MATCH_CSV = "MATCH_CSV"
    AXIS_CSV = "AXIS_CSV"
    REPORT_JSON = "REPORT_JSON"

    METHOD_OPTIONS = [
        "Static labels: use same label state for all EO dates",
        "Nearest label date",
        "Nearest previous label date",
        "Nearest next label date",
        "Validity window: valid_from <= EO <= valid_to",
        "Previous valid state with backtracking",
    ]

    def name(self):
        return "temporal_reconciliation"

    def displayName(self):
        return "Temporal reconciliation: EO dates ↔ label validity"

    def group(self):
        return "3 Temporal"

    def groupId(self):
        return "03_temporal"

    def shortHelpString(self):
        return (
            "Builds an EO date axis and matches labels to acquisition dates. Supports snapshot dates, validity windows, previous/next/nearest matching, tolerance days, and backtracking. "
            "This module can run standalone and outputs CSV/JSON tables for later spatial or UST modules."
        )

    def createInstance(self):
        return TemporalReconciliationAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(self.EO_DATES_TEXT, "EO dates as text/list", defaultValue="", optional=True))
        self.addParameter(QgsProcessingParameterFile(self.EO_DATES_CSV, "EO dates CSV", behavior=QgsProcessingParameterFile.File, extension="csv", optional=True))
        self.addParameter(QgsProcessingParameterString(self.EO_DATE_FIELD, "EO date field in CSV", defaultValue="date", optional=True))
        self.addParameter(QgsProcessingParameterFile(self.EO_RASTER_FOLDER, "Optional EO raster folder; dates parsed from filenames", behavior=QgsProcessingParameterFile.Folder, optional=True))
        self.addParameter(QgsProcessingParameterFile(self.LABEL_TABLE_CSV, "Optional label table CSV", behavior=QgsProcessingParameterFile.File, extension="csv", optional=True))
        self.addParameter(QgsProcessingParameterString(self.LABEL_DATE_FIELD, "Label snapshot/date field", defaultValue="date", optional=True))
        self.addParameter(QgsProcessingParameterString(self.VALID_FROM_FIELD, "Valid-from field", defaultValue="valid_from", optional=True))
        self.addParameter(QgsProcessingParameterString(self.VALID_TO_FIELD, "Valid-to field", defaultValue="valid_to", optional=True))
        self.addParameter(QgsProcessingParameterString(self.LABEL_ID_FIELD, "Label/source ID field", defaultValue="label_id", optional=True))
        self.addParameter(make_advanced(QgsProcessingParameterEnum(self.METHOD, "temporal matching method", self.METHOD_OPTIONS, defaultValue=1)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.TOLERANCE_DAYS, "maximum temporal offset / tolerance [days]", type=QgsProcessingParameterNumber.Integer, minValue=0, maxValue=10000, defaultValue=45)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.BACKTRACK_DAYS, "maximum backtracking window [days]", type=QgsProcessingParameterNumber.Integer, minValue=0, maxValue=10000, defaultValue=365)))
        self.addParameter(make_advanced(QgsProcessingParameterNumber(self.DECAY_HALFLIFE_DAYS, "temporal confidence half-life [days]", type=QgsProcessingParameterNumber.Double, minValue=1.0, maxValue=10000.0, defaultValue=90.0)))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT_FOLDER, "Output folder"))
        self.addOutput(QgsProcessingOutputFolder(self.OUT_FOLDER, "Output folder"))
        self.addOutput(QgsProcessingOutputFile(self.MATCH_CSV, "Temporal match table"))
        self.addOutput(QgsProcessingOutputFile(self.AXIS_CSV, "EO date axis table"))
        self.addOutput(QgsProcessingOutputFile(self.REPORT_JSON, "Report JSON"))

    def processAlgorithm(self, parameters, context, feedback):
        out_dir = resolve_output_folder(self, parameters, self.OUTPUT_FOLDER, context, "helix_temporal")
        eo_field = self.parameterAsString(parameters, self.EO_DATE_FIELD, context) or "date"
        label_date_field = self.parameterAsString(parameters, self.LABEL_DATE_FIELD, context) or "date"
        vf_field = self.parameterAsString(parameters, self.VALID_FROM_FIELD, context) or "valid_from"
        vt_field = self.parameterAsString(parameters, self.VALID_TO_FIELD, context) or "valid_to"
        id_field = self.parameterAsString(parameters, self.LABEL_ID_FIELD, context) or "label_id"
        method = self.parameterAsEnum(parameters, self.METHOD, context)
        tolerance = self.parameterAsInt(parameters, self.TOLERANCE_DAYS, context)
        backtrack = self.parameterAsInt(parameters, self.BACKTRACK_DAYS, context)
        half_life = float(self.parameterAsDouble(parameters, self.DECAY_HALFLIFE_DAYS, context))

        dates = []
        dates += parse_dates_text(self.parameterAsString(parameters, self.EO_DATES_TEXT, context) or "")
        dates += parse_dates_csv(self.parameterAsFile(parameters, self.EO_DATES_CSV, context), eo_field)
        dates += dates_from_folder(self.parameterAsFile(parameters, self.EO_RASTER_FOLDER, context))
        eo_dates = sorted(dict.fromkeys(dates))
        if not eo_dates:
            raise QgsProcessingException("No EO dates found. Provide text, CSV, or an EO raster folder with dates in filenames.")

        label_rows = []
        table = self.parameterAsFile(parameters, self.LABEL_TABLE_CSV, context)
        if table:
            with open(table, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader, 1):
                    snap = parse_date_value(row.get(label_date_field, ""))
                    vf = parse_date_value(row.get(vf_field, ""))
                    vt = parse_date_value(row.get(vt_field, ""))
                    label_rows.append({
                        "label_id": row.get(id_field, f"label_{i}"), "snapshot": snap,
                        "valid_from": vf, "valid_to": vt, "raw": row,
                    })
        else:
            # Static virtual label state
            label_rows = [{"label_id": "static_label", "snapshot": eo_dates[0], "valid_from": None, "valid_to": None, "raw": {}}]
            method = 0

        def days(a, b):
            if a is None or b is None:
                return None
            return abs((a - b).days)

        def signed_days(eo, lab):
            if eo is None or lab is None:
                return None
            return (eo - lab).days

        def temporal_quality(offset_abs):
            if offset_abs is None:
                return 1.0 if method == 0 else 0.0
            # exponential half-life quality; no hard cutoff here, cutoff stored as accepted flag
            import math
            return float(math.exp(-math.log(2.0) * float(offset_abs) / half_life))

        matches = []
        for eo in eo_dates:
            chosen = None
            offset = None
            status = "unmatched"
            candidates = []
            if method == 0:
                chosen = label_rows[0]
                offset = 0
                status = "static"
            elif method == 4:
                for lr in label_rows:
                    vf, vt = lr.get("valid_from"), lr.get("valid_to")
                    if vf and vt and vf <= eo <= vt:
                        candidates.append((0, lr))
                    elif vf and not vt and eo >= vf:
                        candidates.append(((eo - vf).days, lr))
                if candidates:
                    candidates.sort(key=lambda x: x[0])
                    offset, chosen = candidates[0]
                    status = "valid_window"
            else:
                for lr in label_rows:
                    snap = lr.get("snapshot") or lr.get("valid_from")
                    if not snap:
                        continue
                    sd = signed_days(eo, snap)
                    if method == 1:  # nearest
                        candidates.append((abs(sd), lr, sd))
                    elif method == 2 and sd >= 0:  # previous
                        candidates.append((abs(sd), lr, sd))
                    elif method == 3 and sd <= 0:  # next
                        candidates.append((abs(sd), lr, sd))
                    elif method == 5 and 0 <= sd <= backtrack:
                        candidates.append((abs(sd), lr, sd))
                if candidates:
                    candidates.sort(key=lambda x: x[0])
                    offset, chosen, sd = candidates[0]
                    status = "backtracked" if method == 5 and offset > 0 else "matched"

            accepted = bool(chosen is not None and (method in (0, 4, 5) or (offset is not None and offset <= tolerance)))
            if chosen is not None and not accepted:
                status = "outside_tolerance"
            matches.append({
                "eo_date": date_to_iso(eo),
                "matched_label_id": chosen.get("label_id") if chosen else "",
                "label_snapshot": date_to_iso(chosen.get("snapshot")) if chosen else "",
                "valid_from": date_to_iso(chosen.get("valid_from")) if chosen else "",
                "valid_to": date_to_iso(chosen.get("valid_to")) if chosen else "",
                "offset_days_abs": offset if offset is not None else "",
                "accepted": int(accepted),
                "status": status,
                "temporal_quality": round(temporal_quality(offset), 6),
            })

        axis_rows = []
        for idx, d in enumerate(eo_dates):
            prev_delta = "" if idx == 0 else (d - eo_dates[idx - 1]).days
            next_delta = "" if idx == len(eo_dates) - 1 else (eo_dates[idx + 1] - d).days
            axis_rows.append({"index": idx, "date": date_to_iso(d), "year": d.year, "doy": d.timetuple().tm_yday, "delta_prev_days": prev_delta, "delta_next_days": next_delta})

        axis_csv = os.path.join(out_dir, "helix_eo_axis.csv")
        match_csv = os.path.join(out_dir, "helix_temporal_matches.csv")
        write_csv(axis_csv, axis_rows, ["index", "date", "year", "doy", "delta_prev_days", "delta_next_days"])
        write_csv(match_csv, matches, ["eo_date", "matched_label_id", "label_snapshot", "valid_from", "valid_to", "offset_days_abs", "accepted", "status", "temporal_quality"])
        report = {"module": "temporal_reconciliation", "method": self.METHOD_OPTIONS[method], "eo_date_count": len(eo_dates), "label_state_count": len(label_rows), "accepted_count": sum(int(r["accepted"]) for r in matches), "outputs": {"axis_csv": axis_csv, "match_csv": match_csv}}
        json_path = os.path.join(out_dir, "helix_temporal_report.json")
        write_json(json_path, report)
        write_html(os.path.join(out_dir, "helix_temporal_report.html"), "HELIX Temporal Reconciliation", [("Summary", f"<pre>{report}</pre>")])
        safe_feedback(feedback, f"Wrote temporal match table: {match_csv}")
        return {self.OUT_FOLDER: out_dir, self.MATCH_CSV: match_csv, self.AXIS_CSV: axis_csv, self.REPORT_JSON: json_path}
