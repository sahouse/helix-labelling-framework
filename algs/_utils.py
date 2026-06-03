# -*- coding: utf-8 -*-
# Copyright (C) 2026 Sarah Hauser, Karlsruhe Institute of Technology (KIT)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared helpers for HELIX Labelling Framework Processing algorithms."""
from __future__ import annotations

import csv
import json
import math
import os
import re
import tempfile
from datetime import datetime, date
from pathlib import Path

try:
    from qgis.core import (
        QgsProcessingParameterDefinition,
        QgsProcessingUtils,
        QgsProject,
        QgsRasterLayer,
        QgsVectorLayer,
    )
except Exception:  # pragma: no cover - allows syntax checks outside QGIS
    QgsProcessingParameterDefinition = None
    QgsProcessingUtils = None
    QgsProject = None
    QgsRasterLayer = None
    QgsVectorLayer = None

DATE_PATTERNS = (
    re.compile(r"(?P<y>20\d{2}|19\d{2})[-_./]?(?P<m>0[1-9]|1[0-2])[-_./]?(?P<d>0[1-9]|[12]\d|3[01])"),
)


def make_advanced(param):
    """Mark a Processing parameter as advanced without depending on constructor flags."""
    try:
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
    except Exception:
        pass
    return param


def ensure_dir(path: str | os.PathLike | None) -> str:
    p = Path(path) if path else Path(tempfile.mkdtemp(prefix="helix_"))
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def resolve_output_folder(algorithm, parameters, name: str, context, prefix: str) -> str:
    """Resolve FolderDestination, including QGIS TEMPORARY_OUTPUT, to a real directory."""
    try:
        raw = algorithm.parameterAsString(parameters, name, context)
    except Exception:
        raw = parameters.get(name, "")
    if raw is None or str(raw).strip() == "" or str(raw).upper() == "TEMPORARY_OUTPUT":
        if QgsProcessingUtils is not None:
            try:
                tmp = QgsProcessingUtils.generateTempFilename(prefix)
                return ensure_dir(tmp)
            except Exception:
                pass
        return ensure_dir(Path(tempfile.gettempdir()) / prefix)
    return ensure_dir(raw)


def layer_source(layer_or_string):
    """Return a usable data source from a QgsMapLayer or a string path."""
    if layer_or_string is None:
        return ""
    if hasattr(layer_or_string, "source"):
        return layer_or_string.source()
    return str(layer_or_string)


def strip_provider_uri(path: str) -> str:
    # Shapefiles usually arrive plain; geopackages may include |layername=.
    return str(path).split("|", 1)[0]


def parse_date_value(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10] if fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d") else text, fmt).date()
        except Exception:
            pass
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
            except Exception:
                return None
    return None


def date_to_iso(d: date | None) -> str:
    return d.isoformat() if d else ""


def doy_fraction(d: date, year_length: float = 365.2425, origin_doy: float = 1.0) -> float:
    return ((float(d.timetuple().tm_yday) - origin_doy) % year_length) / year_length


def parse_dates_text(text: str) -> list[date]:
    out: list[date] = []
    for token in re.split(r"[,;\n\r\t ]+", text or ""):
        d = parse_date_value(token)
        if d and d not in out:
            out.append(d)
    return sorted(out)


def parse_dates_csv(path: str, field: str = "date") -> list[date]:
    if not path:
        return []
    out: list[date] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        names = reader.fieldnames or []
        use_field = field if field in names else (names[0] if names else field)
        for row in reader:
            d = parse_date_value(row.get(use_field, ""))
            if d and d not in out:
                out.append(d)
    return sorted(out)


def dates_from_folder(folder: str) -> list[date]:
    if not folder or not os.path.isdir(folder):
        return []
    out: list[date] = []
    for root, _, files in os.walk(folder):
        for fn in files:
            if fn.lower().endswith((".tif", ".tiff", ".vrt", ".img", ".jp2", ".csv")):
                d = parse_date_value(fn)
                if d and d not in out:
                    out.append(d)
    return sorted(out)


def write_json(path: str, data) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return path


def write_csv(path: str, rows: list[dict], fieldnames: list[str] | None = None) -> str:
    fieldnames = fieldnames or sorted({k for row in rows for k in row.keys()})
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def add_raster_to_project(path: str, name: str | None = None):
    if not path or QgsProject is None or QgsRasterLayer is None:
        return
    try:
        lyr = QgsRasterLayer(path, name or Path(path).stem)
        if lyr.isValid():
            QgsProject.instance().addMapLayer(lyr)
    except Exception:
        pass


def add_vector_to_project(path: str, name: str | None = None):
    if not path or QgsProject is None or QgsVectorLayer is None:
        return
    try:
        lyr = QgsVectorLayer(path, name or Path(path).stem, "ogr")
        if lyr.isValid():
            QgsProject.instance().addMapLayer(lyr)
    except Exception:
        pass




def normalise_source_value(value) -> str:
    """Return a stable text representation for class schema source values."""
    if value is None:
        return ""
    text = str(value).strip()
    # GDAL/CSV often turns integer categories into 1.0; normalize aliases.
    try:
        f = float(text)
        if math.isfinite(f) and abs(f - int(f)) < 1e-9:
            return str(int(f))
    except Exception:
        pass
    return text


def numeric_class_id(value) -> int | None:
    """Return an integer class ID for numeric category values, otherwise None."""
    try:
        if value is None:
            return None
        f = float(str(value).strip())
        if math.isfinite(f) and abs(f - int(f)) < 1e-9:
            return int(f)
    except Exception:
        pass
    return None


def source_value_aliases(value) -> list[str]:
    """Aliases used when matching schema source values to vector/raster values."""
    aliases = []
    raw = "" if value is None else str(value).strip()
    norm = normalise_source_value(value)
    for item in (raw, norm):
        if item != "" and item not in aliases:
            aliases.append(item)
    n = numeric_class_id(value)
    if n is not None:
        for item in (str(n), str(float(n))):
            if item not in aliases:
                aliases.append(item)
    return aliases


def next_free_class_id(used_ids, start: int = 1, avoid_ids=None) -> int:
    """Return the next positive integer not already used/reserved."""
    used = {int(v) for v in (used_ids or []) if v is not None}
    avoid = {int(v) for v in (avoid_ids or []) if v is not None}
    cid = max(1, int(start))
    while cid in used or cid in avoid:
        cid += 1
    return cid

def load_class_ids(text: str, arrays=None, nodata=0) -> list[int]:
    ids: list[int] = []
    for token in re.split(r"[,;\s]+", text or ""):
        if not token:
            continue
        try:
            ids.append(int(float(token)))
        except Exception:
            pass
    if ids:
        return sorted(dict.fromkeys(ids))
    if arrays is not None:
        try:
            import numpy as np
            vals = []
            for arr in arrays:
                u = np.unique(arr)
                vals.extend([int(v) for v in u.tolist() if int(v) != int(nodata)])
            ids = sorted(dict.fromkeys(vals))
        except Exception:
            ids = []
    return ids


def read_class_map_csv(path: str) -> dict[int, str]:
    if not path:
        return {}
    out: dict[int, str] = {}
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                keys = {k.lower(): k for k in row.keys()}
                id_key = keys.get("id") or keys.get("class_id") or keys.get("value") or next(iter(row.keys()))
                name_key = keys.get("name") or keys.get("class") or keys.get("label")
                try:
                    cid = int(float(row.get(id_key, "")))
                    out[cid] = row.get(name_key, str(cid)) if name_key else str(cid)
                except Exception:
                    pass
    except Exception:
        pass
    return out



def safe_slug(value, max_len: int = 64) -> str:
    """Return a short ASCII-ish token for band descriptions and schema names."""
    text = str(value if value is not None else "").strip()
    if not text:
        text = "class"
    text = re.sub(r"[^0-9A-Za-z_\-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_") or "class"
    return text[:max_len]


def infer_common_field(field_names, preferred=None) -> str:
    """Choose a likely class field from a field-name list."""
    names = list(field_names or [])
    if preferred and preferred in names:
        return preferred
    for candidate in ("KlasseID", "class_id", "ClassID", "CLASS_ID", "class", "Class", "klasse", "Klasse", "label", "Label", "name", "Name", "id", "ID"):
        if candidate in names:
            return candidate
    return preferred or (names[0] if names else "")


def read_class_schema(path: str) -> dict:
    """Read a HELIX class schema CSV/JSON.

    Returns a dict with keys:
      rows, class_ids, class_names, source_to_id, include, merge_to, quality_q, priority
    The function accepts both the new HELIX schema columns and older simple class maps.
    """
    result = {
        "rows": [],
        "class_ids": [],
        "class_names": {},
        "source_to_id": {},
        "include": {},
        "merge_to": {},
        "quality_q": {},
        "priority": {},
    }
    if not path:
        return result
    try:
        if str(path).lower().endswith(".json"):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            rows = data.get("classes", data if isinstance(data, list) else [])
        else:
            with open(path, newline="", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
    except Exception:
        return result
    for row in rows:
        if not isinstance(row, dict):
            continue
        keys = {str(k).lower(): k for k in row.keys()}
        id_key = keys.get("class_id") or keys.get("id") or keys.get("value")
        if not id_key:
            continue
        try:
            cid = int(float(row.get(id_key, "")))
        except Exception:
            continue
        name_key = keys.get("class_name") or keys.get("name") or keys.get("class") or keys.get("label")
        src_key = keys.get("source_value") or keys.get("source") or keys.get("original_value") or keys.get("raw_value")
        inc_key = keys.get("include") or keys.get("use")
        merge_key = keys.get("merge_to") or keys.get("map_to") or keys.get("target_id")
        q_key = keys.get("quality_q") or keys.get("q") or keys.get("quality")
        pr_key = keys.get("priority")
        class_name = str(row.get(name_key, f"class_{cid}")) if name_key else f"class_{cid}"
        source_value = str(row.get(src_key, class_name if name_key else cid)) if src_key or name_key else str(cid)
        include = True
        if inc_key:
            include = str(row.get(inc_key, "1")).strip().lower() not in ("0", "false", "no", "n", "exclude")
        try:
            merge_to = int(float(row.get(merge_key, cid))) if merge_key and str(row.get(merge_key, "")).strip() != "" else cid
        except Exception:
            merge_to = cid
        try:
            quality = float(row.get(q_key, 1.0)) if q_key else 1.0
        except Exception:
            quality = 1.0
        try:
            priority = float(row.get(pr_key, 1.0)) if pr_key else 1.0
        except Exception:
            priority = 1.0
        result["rows"].append({
            "class_id": cid,
            "class_name": class_name,
            "source_value": source_value,
            "include": 1 if include else 0,
            "merge_to": merge_to,
            "priority": priority,
            "quality_q": quality,
        })
        result["class_names"][cid] = class_name
        for alias in source_value_aliases(source_value):
            result["source_to_id"][alias] = cid
        for alias in source_value_aliases(cid):
            result["source_to_id"][alias] = cid
        result["include"][cid] = include
        result["merge_to"][cid] = merge_to
        result["quality_q"][cid] = quality
        result["priority"][cid] = priority
    result["class_ids"] = sorted(dict.fromkeys(int(r["class_id"]) for r in result["rows"]))
    return result


def band_description(cid, class_names=None, suffix: str = "") -> str:
    """Build stable class-aware raster band descriptions."""
    name = (class_names or {}).get(int(cid), f"class_{cid}")
    tail = ("_" + safe_slug(suffix, 32)) if suffix else ""
    return f"class_{int(cid)}_{safe_slug(name)}{tail}"

def safe_feedback(feedback, msg: str):
    try:
        feedback.pushInfo(str(msg))
    except Exception:
        pass


def write_html(path: str, title: str, sections: list[tuple[str, str]]) -> str:
    body = ["<!doctype html><html><head><meta charset='utf-8'>",
            f"<title>{title}</title>",
            "<style>body{font-family:Arial,sans-serif;margin:2rem;line-height:1.45}table{border-collapse:collapse;margin:.5rem 0 1.5rem 0}td,th{border:1px solid #ddd;padding:.35rem .55rem}th{background:#f3f6f4}code{background:#f4f4f4;padding:.1rem .25rem}.ok{color:#26734d}.warn{color:#a35a00}</style>",
            "</head><body>", f"<h1>{title}</h1>"]
    for heading, html in sections:
        body.append(f"<h2>{heading}</h2>\n{html}")
    body.append("</body></html>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(body))
    return path
