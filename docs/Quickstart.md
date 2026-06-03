# HELIX Quickstart

## Only convert a shapefile to the EO grid

1. Open **HELIX Labelling Framework → Spatial reconstruction**.
2. Select the EO/reference grid raster.
3. Select the vector label layer.
4. Set `Class field`, for example `KlasseID` or `class_id`.
5. Leave all advanced output checkboxes off.
6. Run.

Main result: `helix_label_hard.tif`.

## Avoid typing class IDs

1. Run **Preflight & class schema** first.
2. It writes `helix_class_schema.csv`.
3. Edit this CSV if needed.
4. Use it as `Class schema CSV` in Spatial Reconstruction.

## Build ML-ready supervision

Run modules in this order:

1. Preflight & class schema
2. Spatial reconstruction
3. Temporal reconciliation, if dates matter
4. Helical / wave features, if seasonal time matters
5. Context & risk features
6. Soft targets & weights / UST
7. Export & report


## Create real per-class context features

After Spatial Reconstruction, use `helix_label_hard.tif` as the hard label raster in **Context & risk features**. For a 10-class hard raster, enable:

- `write multi-radius per-class neighbourhood support stack`
- `additional/multi radii`, for example `2,5,10`
- optionally `write class-pair context stack` for features such as class A near class B

Main outputs:

- `helix_context_class_support_multiradius.tif`: one band per class and radius.
- `helix_context_local_purity_multiradius.tif`: one purity band per radius.
- `helix_context_class_pair_context.tif`: optional ordered class-neighbourhood interaction bands.

## Create class × helical features from hard labels

In **Helical / wave features**, enable `write class × helical interaction stacks`. You can now provide either:

- a class/soft-target stack, or
- the single-band `helix_label_hard.tif`, which HELIX one-hot encodes internally.

## Notes for mixed class schemas

- Numeric classes and string classes can be mixed; HELIX avoids automatic ID collisions.
- Raster label sources can be remapped through `source_value → class_id` in the class schema CSV.
- The final hard raster uses the configured `Final background / no-label value` for pixels without accepted label support.
