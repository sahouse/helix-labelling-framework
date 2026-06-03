# HELIX Labelling Framework – Parameter Reference

## General units

| Parameter type | Unit / convention |
|---|---|
| CRS, extent, pixel size | inherited from the EO/reference grid |
| Neighbourhood radius | pixels |
| Temporal tolerance/backtracking | days |
| Probabilities, purity, agreement, uncertainty, quality Q | 0–1 unless the input raster is 0–100, which HELIX normalizes internally |
| Hard class raster | one band, integer class IDs |
| Class/probability/soft stacks | one band per class |

## Preflight & class schema

- **Primary vector label layer**: enables QGIS field dropdowns.
- **Class field**: attribute containing the class value; can be numeric or string.
- **Class-name field**: optional human-readable class names.
- **Optional existing class schema CSV**: reuse/edit previous schema.

## Spatial reconstruction

- **Spatial method**: choose minimal hard raster, vector mode, raster mode, fusion, or dry run.
- **Fusion rule**: first valid, last valid, majority vote, or class-weighted support using schema `priority × quality_q`.
- **Class selection**: all detected, explicit `CLASS_IDS`, or included classes from schema.
- **Write one-hot class stack**: optional one band per class.
- **Write class probability/support stack**: optional class support from multiple sources.
- **Write per-source label stack**: optional one band per input source.
- **Final background / no-label value**: value written where no class passes source coverage/filtering.
- **NoData/background value**: source NoData value used while rasterizing/aligning inputs.
- **Supersampling factor**: compatibility placeholder in this release; true area-fraction supersampling is not yet applied.

## Context & risk

- **Class schema CSV**: optional; lets Context name per-class output bands correctly.
- **Main neighbourhood radius**: pixel radius for global edge/diversity features.
- **Additional/multi radii**: comma-separated pixel radii, e.g. `2,5,10`, used for per-class support, local purity and class-pair context. Empty means use the main radius only.
- **Neighbourhood window shape**: square window or circular/disk window.
- **Write multi-radius per-class neighbourhood support stack**: optional one band per class and radius.
- **Write local purity/dominance stack**: optional one band per radius, containing the local top-class support.
- **Write class-pair context stack**: optional ordered class interaction features. A band `class_A_near_class_B_R5` means focal/centre support of class A multiplied by neighbourhood support of class B within radius 5.
- **Maximum class-pair bands**: safety limit to avoid accidentally writing thousands of bands for many classes/radii.

## Soft targets & weights

- **Class schema CSV**: optional; lets UST name class bands correctly.
- **Hard-label input interpretation**: single-band class IDs or multi-band one-hot/support stack.
- **Alpha/base smoothing**: minimum softening.
- **Beta terms**: how strongly edge, temporal, source, or context risk increase smoothing/reduce weights.
- **Quality prior Q**: global label/source quality prior; schema `quality_q` values additionally reduce effective class/pixel quality when provided.
- **Temporal match CSV**: optional table from Temporal Reconciliation; HELIX uses the mean accepted `temporal_quality` as a global temporal risk signal.
- **Per-class outputs**: optional class confidence, uncertainty, and weight stacks.

## Helical / wave features

- **EO dates**: provide text, CSV, or a raster folder with dates in filenames.
- **Fill in-between dates**: optional regular date grid in days.
- **Write constant raster feature stacks**: writes date features aligned to the reference grid.
- **Write class × helical interaction stacks**: multiplies each class band with cyclic/relative time features. The class input can be a class/soft-target stack or a single-band hard label raster that HELIX one-hot encodes internally.
- **Class schema CSV / Class IDs**: optional; used to name and order hard-label interaction bands.
