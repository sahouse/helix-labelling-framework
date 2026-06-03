# -*- coding: utf-8 -*-
# Copyright (C) 2026 Sarah Hauser, Karlsruhe Institute of Technology (KIT)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon
from pathlib import Path

from .algs.preflight_schema import PreflightSchemaAlgorithm
from .algs.spatial_reconstruction import SpatialReconstructionAlgorithm
from .algs.temporal_reconciliation import TemporalReconciliationAlgorithm
from .algs.helical_features import HelicalFeaturesAlgorithm
from .algs.context_features import ContextFeaturesAlgorithm
from .algs.soft_supervision import SoftSupervisionAlgorithm
from .algs.export_report import ExportReportAlgorithm
from .algs.batch_recipe import BatchRecipeAlgorithm


class HelixLabelPreprocessorProvider(QgsProcessingProvider):
    def id(self):
        return "helix"

    def name(self):
        return "HELIX Labelling Framework"

    def longName(self):
        return "HELIX Labelling Framework - modular EO label preparation"

    def icon(self):
        return QIcon(str(Path(__file__).resolve().parent / "icon.png"))

    def loadAlgorithms(self):
        for alg in [
            PreflightSchemaAlgorithm(),
            SpatialReconstructionAlgorithm(),
            TemporalReconciliationAlgorithm(),
            HelicalFeaturesAlgorithm(),
            ContextFeaturesAlgorithm(),
            SoftSupervisionAlgorithm(),
            ExportReportAlgorithm(),
            BatchRecipeAlgorithm(),
        ]:
            self.addAlgorithm(alg)
