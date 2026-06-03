# HELIX Labelling Framework – User Guide

Version 1.0.0.

HELIX Labelling Framework is a modular QGIS toolbox for preparing heterogeneous Earth Observation label sources as EO-grid-aligned, time-aware, context-aware, uncertainty-aware supervision products for ML/AI workflows.

## Core rules

- Spatial Reconstruction writes a single-band hard class-ID raster by default.
- Optional stacks are only written when selected.
- String class attributes are mapped automatically to integer class IDs.
- Preflight and Spatial write a reusable `helix_class_schema.csv` and `helix_class_schema.json`.
- Context and Soft Targets can read the schema so per-class stacks keep correct class IDs, names, and band descriptions.
- Plugin-owned labels are English. QGIS may still translate its own Advanced section depending on the UI language.

## Class schema

If a vector class field contains values such as `building`, `tree`, or `water`, HELIX maps them to integer IDs and stores the mapping:

```csv
class_id,class_name,source_value,source_type,include,merge_to,priority,quality_q
1,building,building,vector,1,1,1.0,1.0
2,tree,tree,vector,1,2,1.0,1.0
3,water,water,vector,1,3,1.0,1.0
```

The raster stores numeric class IDs. The schema stores what the IDs mean.

## Module responsibility

| Module | Main responsibility |
|---|---|
| Preflight & class schema | Inspect fields, CRS, class values, raster metadata, schema. |
| Spatial reconstruction | Align vector/raster labels to an EO/reference grid. |
| Temporal reconciliation | Match EO dates with label dates/validity windows. |
| Helical / wave features | Create cyclic seasonal time features and optional class × temporal interaction stacks. |
| Context & risk | Create boundary, diversity, entropy, margin, multi-radius per-class context and class-pair context layers. |
| Soft targets & weights | Create UST: soft targets, uncertainty and training weights. |
| Export & report | Bundle outputs and write manifest/report. |

## Spatial outputs

Default:

- `helix_label_hard.tif`: one band, pixel value = class ID.
- `helix_class_schema_detected.csv/json`: class mapping.
- `helix_spatial_report.json/html`: report.

Optional:

- `helix_spatial_class_stack.tif`: one-hot one band per class.
- `helix_spatial_probabilities.tif`: class support/probability one band per class.
- `helix_spatial_source_labels.tif`: one band per input source.
- `helix_spatial_source_agreement.tif`: global agreement raster.
- `helix_spatial_purity.tif`: global top-class dominance.

## Context and UST

Context can output global risk layers and real class-wise context features. From a single-band hard class raster, HELIX internally builds class masks; from a probability/soft-target stack, it uses soft class support directly. Advanced Context outputs include:

- `helix_context_class_support_multiradius.tif`: one band per class and radius, e.g. class 3 support within radius 10 pixels.
- `helix_context_local_purity_multiradius.tif`: one local top-class support/purity band per radius.
- `helix_context_class_pair_context.tif`: optional ordered class-pair features, e.g. class A near class B.

UST writes soft targets one band per class, plus overall uncertainty and overall weights. Optional advanced outputs include per-class confidence, uncertainty, and weights.

## Helical features

Helical features are date/time features by default: annual and multi-harmonic sine/cosine waves, phase, and date-spacing information. Optional class × helical interactions multiply class/soft-target bands with helical feature values for advanced ML workflows. If no class/soft-target stack is available, the module can now use the single-band hard class raster and one-hot encode it internally.
