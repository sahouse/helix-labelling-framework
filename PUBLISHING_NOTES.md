# Publishing notes for HELIX Labelling Framework 1.0.0

Before uploading to the official QGIS plugin repository, replace the placeholder URLs in `metadata.txt` and `README.md` with your real public repository URLs.

No local Git installation is strictly required. You can create a repository in GitHub or GitLab in the browser and upload the source files with the web interface. What matters for QGIS approval is that the repository is publicly accessible, contains the plugin source code, and is not only a ZIP archive.

Recommended metadata URL pattern:

```ini
homepage=https://github.com/sahouse/helix-labelling-framework#readme
tracker=https://github.com/sahouse/helix-labelling-framework/issues
repository=https://github.com/sahouse/helix-labelling-framework
```

Versioning: metadata uses `1.0.0`, the semantic-versioning form of release 1.0. Future updates should use increasing versions such as `1.0.1`, `1.1.0`, or `2.0.0`.

QGIS compatibility: this package declares `qgisMinimumVersion=3.34` and `qgisMaximumVersion=4.99`. Keep this only if you have tested the plugin in QGIS 4 / Qt 6. If you want a conservative QGIS 3-only release, change `qgisMaximumVersion=3.99` before upload.

Runtime dependencies: QGIS/PyQGIS, GDAL and NumPy, normally included in standard QGIS installations on Windows, Linux and macOS.
