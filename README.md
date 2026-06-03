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

The metadata declares compatibility with QGIS 3.34+ and QGIS 4.x (`qgisMaximumVersion=4.99`). Before public upload, test installation and a small sample workflow in your target QGIS versions, especially QGIS 4, because QGIS 4 uses Qt 6.

## Public repository without local Git

A local Git command-line workflow is not required for publication, but the QGIS plugin repository requires a publicly accessible source-code repository and an issue tracker. You can create a GitHub or GitLab repository in the browser, upload the source files through the web interface, enable Issues, and then use the repository README as the plugin homepage. Do not use a repository that only contains the plugin ZIP.

## Support and issue reporting

Please report issues through the repository issue tracker:

https://github.com/sahouse/helix-labelling-framework/issues

## Citation / attribution

Author: Sarah Hauser, Karlsruhe Institute of Technology (KIT)  
Contact: sarah.hauser@kit.edu

## License

This plugin is released under the GNU General Public License v3.0 or later.
