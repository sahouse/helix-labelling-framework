# -*- coding: utf-8 -*-
# Copyright (C) 2026 Sarah Hauser, Karlsruhe Institute of Technology (KIT)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import webbrowser
from pathlib import Path

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QToolBar
from qgis.core import QgsApplication

from .helix_label_preprocessor_provider import HelixLabelPreprocessorProvider


class HelixLabelPreprocessor:
    """QGIS plugin front-end for HELIX Labelling Framework.

    Robustness notes:
    - The toolbar/menu actions never refresh/remove a stored Processing provider on click.
      In QGIS, Processing providers are C++ objects; after plugin reloads the old Python
      wrapper may still exist but the C++ object can already be deleted.
    - Actions therefore resolve algorithms from the registry and only register a fresh
      provider if the registry has no HELIX provider at all.
    - Duplicate HELIX menus are almost always caused by multiple HELIX plugin folders.
      The code avoids addToolBarIcon() and creates only one custom toolbar per plugin.
    """

    PROVIDER_ID = "helix"

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self._owns_provider = False
        self.actions = []
        self.toolbar = None
        self.plugin_dir = Path(__file__).resolve().parent
        self.menu_name = "&HELIX Labelling Framework"

    def initGui(self):
        # Register the Processing provider, but do not delete/refresh stale provider
        # wrappers from action callbacks later.
        self._ensure_provider()

        # Remove a leftover toolbar with our object name in the same QGIS session.
        # This is only a visual cleanup; duplicate menu entries after restart mean
        # multiple HELIX plugin folders are installed.
        try:
            old_toolbar = self.iface.mainWindow().findChild(QToolBar, "HELIXLabellingFrameworkToolbar")
            if old_toolbar is not None:
                old_toolbar.clear()
                old_toolbar.deleteLater()
        except Exception:
            pass

        # One dedicated toolbar only. No addToolBarIcon() calls.
        self.toolbar = self.iface.addToolBar("HELIX Labelling Framework")
        self.toolbar.setObjectName("HELIXLabellingFrameworkToolbar")

        # Main standalone modules. Expert batch runner stays in the Processing toolbox.
        self._add_algorithm_action("icons/module_preflight.svg", "Preflight & class schema", "helix:preflight_schema")
        self._add_algorithm_action("icons/module_spatial.svg", "Spatial reconstruction", "helix:spatial_reconstruction")
        self._add_algorithm_action("icons/module_temporal.svg", "Temporal reconciliation", "helix:temporal_reconciliation")
        self._add_algorithm_action("icons/module_helical.svg", "Helical / wave features", "helix:helical_features")
        self._add_algorithm_action("icons/module_context.svg", "Context & risk features", "helix:context_features")
        self._add_algorithm_action("icons/module_supervision.svg", "Soft targets & weights", "helix:soft_supervision")
        self._add_algorithm_action("icons/module_export.svg", "Export & report", "helix:export_report")
        self._add_doc_action()

    def unload(self):
        for action in list(self.actions):
            try:
                self.iface.removePluginMenu(self.menu_name, action)
            except Exception:
                pass
            try:
                if self.toolbar is not None:
                    self.toolbar.removeAction(action)
            except Exception:
                pass
        self.actions.clear()

        if self.toolbar is not None:
            try:
                self.toolbar.clear()
                self.toolbar.deleteLater()
            except Exception:
                pass
            self.toolbar = None

        # Only remove the provider if this plugin instance created it and the C++ object
        # still exists. This avoids the common "wrapped C/C++ object ... has been deleted"
        # crash after plugin reloads.
        if self.provider is not None and self._owns_provider and not self._is_deleted(self.provider):
            try:
                QgsApplication.processingRegistry().removeProvider(self.provider)
            except Exception:
                pass
        self.provider = None
        self._owns_provider = False

    def _is_deleted(self, obj) -> bool:
        try:
            from qgis.PyQt import sip
            return bool(sip.isdeleted(obj))
        except Exception:
            return False

    def _ensure_provider(self):
        registry = QgsApplication.processingRegistry()

        # If a valid HELIX provider is already registered, use it. This prevents two
        # installed HELIX folders from fighting over provider ownership.
        try:
            existing = registry.providerById(self.PROVIDER_ID)
        except Exception:
            existing = None

        if existing is not None and not self._is_deleted(existing):
            self.provider = existing
            self._owns_provider = False
            return existing

        provider = HelixLabelPreprocessorProvider()
        ok = registry.addProvider(provider)
        if ok is False:
            # Some QGIS builds return None on success, False on failure.
            raise RuntimeError("QGIS refused to register the HELIX Processing provider.")
        self.provider = provider
        self._owns_provider = True
        return provider

    def _icon(self, rel):
        p = self.plugin_dir / rel
        return QIcon(str(p if p.exists() else self.plugin_dir / "icon.png"))

    def _add_algorithm_action(self, icon_rel, text, alg_id):
        action = QAction(self._icon(icon_rel), text, self.iface.mainWindow())
        action.setObjectName("HELIX_" + alg_id.replace(":", "_"))
        action.setToolTip(f"Open {text} ({alg_id})")
        action.triggered.connect(lambda _checked=False, aid=alg_id: self._open_algorithm(aid))
        self.iface.addPluginToMenu(self.menu_name, action)
        if self.toolbar is not None:
            self.toolbar.addAction(action)
        self.actions.append(action)
        return action

    def _add_doc_action(self):
        action = QAction(self._icon("icons/module_help.svg"), "Open HELIX user guide", self.iface.mainWindow())
        action.setObjectName("HELIX_open_user_guide")
        action.setToolTip("Open the local HELIX Labelling Framework user guide")
        action.triggered.connect(self._open_docs)
        self.iface.addPluginToMenu(self.menu_name, action)
        if self.toolbar is not None:
            self.toolbar.addAction(action)
        self.actions.append(action)

    def _open_algorithm(self, alg_id: str):
        registry = QgsApplication.processingRegistry()
        alg = registry.algorithmById(alg_id)

        if alg is None:
            # Register a fresh provider only if the registry does not currently know HELIX.
            # Do not remove/refresh self.provider here; it may be a deleted C++ wrapper.
            try:
                self._ensure_provider()
                alg = registry.algorithmById(alg_id)
            except Exception as exc:
                self.iface.messageBar().pushCritical(
                    "HELIX Labelling Framework",
                    f"Could not register the HELIX Processing provider before opening {alg_id}: {exc}",
                )
                return

        if alg is None:
            self.iface.messageBar().pushCritical(
                "HELIX Labelling Framework",
                f"Processing algorithm not registered: {alg_id}. Restart QGIS and make sure only one HELIX plugin folder is installed.",
            )
            return

        try:
            import processing  # QGIS Processing module
            try:
                processing.execAlgorithmDialog(alg_id, {})
            except TypeError:
                # Some QGIS builds expose a one-argument wrapper.
                processing.execAlgorithmDialog(alg_id)
        except Exception as exc:
            self.iface.messageBar().pushCritical(
                "HELIX Labelling Framework",
                f"Could not open {alg_id}: {exc}",
            )

    def _open_docs(self):
        # Prefer the polished HTML guide for QGIS users; keep Markdown as a developer/GitHub fallback.
        for rel in ("docs/HELIX_User_Guide.html", "docs/index.html", "docs/HELIX_User_Guide.md"):
            doc = self.plugin_dir / rel
            if doc.exists():
                webbrowser.open(doc.as_uri())
                return
        self.iface.messageBar().pushWarning("HELIX Labelling Framework", "User guide not found in plugin docs folder.")
