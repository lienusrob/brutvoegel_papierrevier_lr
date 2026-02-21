# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingProvider, QgsApplication
from .brutvoegel_algorithm import BrutvoegelAlgorithm
from qgis.PyQt.QtGui import QIcon

class BrutvoegelProvider(QgsProcessingProvider):
    def __init__(self):
        QgsProcessingProvider.__init__(self)
    def loadAlgorithms(self):
        self.addAlgorithm(BrutvoegelAlgorithm())
    def id(self):
        return 'brutvoegel_lr_provider'
    def name(self):
        return 'Brutvögel_Papierrevier_LR'
    def icon(self):
        return QIcon()

class BrutvoegelPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
    def initGui(self):
        self.provider = BrutvoegelProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)
    def unload(self):
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
