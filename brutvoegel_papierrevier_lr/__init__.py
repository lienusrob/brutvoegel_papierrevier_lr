# -*- coding: utf-8 -*-
def classFactory(iface):
    from .brutvoegel_provider import BrutvoegelPlugin
    return BrutvoegelPlugin(iface)
