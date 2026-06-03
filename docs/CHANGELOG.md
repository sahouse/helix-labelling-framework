# Changelog

## 1.0.0

- First stable public-release version.
- Metadata prepared for QGIS 3.34+ and QGIS 4.x (`qgisMaximumVersion=4.99`).
- README can be used as plugin homepage when hosted in a public source repository.
- Runtime dependencies documented as QGIS/PyQGIS, GDAL and NumPy.

- Context module now supports true multi-radius per-class neighbourhood support stacks. A single hard class-ID raster with N classes can become N × R context bands, one class per radius.
- Context module now supports optional ordered class-pair context stacks (`class A near class B`) for boundary/neighbourhood interaction features between classes.
- Context module supports square or circular/disk neighbourhood windows and reports truncation if class-pair output would exceed the configured band limit.
- Helical Features now accepts a single-band hard label raster for class × helical interactions and internally one-hot encodes it when no class/soft-target stack is provided.
- Updated documentation to clarify the distinction between Spatial Reconstruction as grid alignment and Context/Helical modules as feature enrichment.

## 4.3.8
- Fixed mixed numeric/string class schemas: automatic string IDs now avoid collisions with existing numeric class IDs.
- Spatial Reconstruction now applies class-schema `source_value → class_id` remapping to raster label inputs, not only vector labels.
- Implemented the Spatial `Final background / no-label value` as the final hard-label background value.
- Clarified supersampling as a compatibility placeholder; categorical rasterisation/alignment still uses GDAL rasterize/warp.
- Renamed the fourth fusion rule to class-weighted support and implemented schema `priority × quality_q` weighting.
- Helical raster outputs now fail with a clear message if no reference grid is selected.
- Soft Targets & Weights can consume the Temporal Reconciliation match CSV as a global temporal-quality signal.
- Soft Targets & Weights now applies schema `quality_q` to effective Q, per-class confidence and per-class weights.
- Added stronger grid/band-count checks for ancillary Context/UST rasters.

## 4.3.7
- Added automatic mapping for string class attributes in vector labels. String values such as `building`, `tree` or `water` are converted to stable integer class IDs before rasterisation.
- Preflight and Spatial now write both `helix_class_schema.csv` and `helix_class_schema.json` with `class_id`, `class_name`, `source_value`, `include`, `merge_to`, `priority` and `quality_q`.
- Spatial Reconstruction can optionally write a one-hot class stack while still using a one-band hard class-ID raster by default.
- Context and Soft Targets can read the class schema so per-class stacks keep the correct class IDs/names and band descriptions.
- Helical class-interaction stacks now inherit class/soft-target band descriptions where available.
- Removed plugin-owned German/English mixed labels such as `Erweitert:`; QGIS may still translate its own Advanced section depending on the UI language.


## 4.3.5
- Added optional per-class confidence, per-class uncertainty and per-class weight stacks in Soft Targets & Weights (UST).
- Added explicit hard-label input interpretation for single-band class-ID rasters versus multi-band one-hot/hard class stacks.
- Soft targets remain one band per class; overall uncertainty and overall weights remain the recommended default outputs.
- Added optional class × helical interaction stacks for advanced workflows that combine soft/class bands with cyclic HELIX wave features.

## 4.3.4

- Removed user-guide meta text about HTML/Markdown.
- Removed concrete global-product example and kept the documentation general.
- Added richer units/conventions documentation.
- Added primary vector-layer inputs so QGIS can show class-field dropdown menus.
- Moved additional vector layers to the Advanced section.
- Updated module icons to a consistent green/white visual style.

## 4.3.1

- Added detailed HTML user guide for QGIS users.
- Help action opens `docs/HELIX_User_Guide.html` first, with Markdown fallback.

## 4.3.0

- Refactored Spatial Reconstruction to be modular.
- Spatial now writes only `helix_label_hard.tif`, schema and report by default.
- Probability, coverage and source-agreement are optional advanced spatial outputs.
- Edge risk belongs to Context & Risk Features.
- Confidence, uncertainty, weights and soft targets belong to Soft Targets & Weights / UST.
- Preflight writes `helix_class_schema.csv`.


## 4.3.6
- Spatial Reconstruction now optionally writes per-source label stacks and spatial purity while keeping one-band hard labels as default.
- Context module can write per-class neighbourhood support stacks and local purity rasters.
- Soft Targets & Weights can consume source-agreement and per-class context stacks as additional risk terms.
- Helical Features can fill in-between dates with a configurable day step and retains optional class × helical interaction stacks.
