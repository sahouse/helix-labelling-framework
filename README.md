# HELIX Labelling Framework

Copyright (C) 2026 Sarah Hauser, Karlsruhe Institute of Technology (KIT)  
License: GPL-3.0-or-later

HELIX Labelling Framework is a modular QGIS Processing toolbox for preparing heterogeneous Earth Observation label sources as EO-grid-aligned, time-aware, context-aware and uncertainty-aware supervision products for machine-learning workflows.

## What the plugin does

The framework helps convert vector or raster labels into products that can be used consistently with Earth Observation feature grids. It focuses on transparent, auditable label preparation rather than treating labels as perfect, timeless class values.

Core modules:

1. **Preflight & class schema**:  inspect label classes, create stable class IDs and prepare schema files.
2. **Spatial reconstruction**: align vector/raster labels to an EO target grid.
3. **Temporal reconciliation**: match labels to EO acquisition times using static, snapshot or validity-window logic.
4. **Helical / wave features**:  derive temporal and class-interaction features from label stacks.
5. **Context & risk features**: build class-aware neighbourhood, purity and ambiguity indicators.
6. **Soft targets & weights**: create uncertainty-aware supervision layers for ML training.
7. **Export & report**: write ML-ready raster stacks and readable processing reports.

## Installation

Download the QGIS plugin ZIP and install it via:

`QGIS → Plugins → Manage and Install Plugins → Install from ZIP`

For a clean local reinstall during development, remove any older HELIX plugin folder from the QGIS profile first, then restart QGIS.

## Usage

After installation, open the tools from the QGIS Processing toolbox or from the **HELIX Labelling Framework** menu/toolbar.

Recommended first workflow:

1. Run **Preflight & class schema** on your label source.
2. Run **Spatial reconstruction** using your EO grid as reference.
3. Optionally run **Temporal reconciliation** if label timing matters.
4. Add **Context & risk features** and/or **Helical / wave features** if needed.
5. Generate **Soft targets & weights**.
6. Run **Export & report** for a final manifest and documentation bundle.

Detailed local documentation is also included under `docs/`:

- `docs/HELIX_User_Guide.html`
- `docs/Quickstart.md`
- `docs/Parameter_Reference.md`
- `docs/CHANGELOG.md`

## Dependencies and platform support

Required runtime components are QGIS/PyQGIS, GDAL and NumPy. These are normally included in standard QGIS installations on Windows, Linux and macOS. The plugin avoids hard-coded operating-system paths and uses the QGIS `qgis.PyQt` compatibility layer instead of direct PyQt5/PyQt6 imports.

## Support and issue reporting

Please report issues through the repository issue tracker:

https://github.com/sahouse/helix-labelling-framework/issues

## Citation / attribution

Author: Sarah Hauser, Karlsruhe Institute of Technology (KIT)  
Contact: sarah.hauser@kit.edu

If you use the HELIX Labelling Framework or build upon its concepts, please cite:

Hauser, S.; Augner, L.; Schmitt, A. Perfect Labelling: A Review and Outlook of Label Optimization Techniques in Dynamic Earth Observation. *Remote Sensing* 2025, 17, 1246. https://doi.org/10.3390/rs17071246

Hauser, S. Automated Feature and Label Refinement in the Context of Environmental Monitoring by Multi-Modal Satellite Data. PhD thesis, Karlsruhe Institute of Technology (KIT), 2025. https://doi.org/10.5445/IR/1000185980

## License

This plugin is released under the GNU General Public License v3.0 or later.
