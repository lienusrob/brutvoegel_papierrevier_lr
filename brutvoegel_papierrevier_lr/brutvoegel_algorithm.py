# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QCoreApplication, QVariant, QDate, QDateTime
from qgis.core import (QgsProcessing, QgsFeature, QgsGeometry, QgsFields, QgsField, 
                       QgsProcessingAlgorithm, QgsCoordinateReferenceSystem, 
                       QgsCoordinateTransform, QgsProcessingParameterFeatureSource, 
                       QgsProcessingParameterDistance, QgsProcessingParameterNumber, 
                       QgsProcessingParameterField, QgsProcessingParameterFeatureSink, 
                       QgsWkbTypes)
import math
import re

class BrutvoegelAlgorithm(QgsProcessingAlgorithm):
    def tr(self, string):
        return QCoreApplication.translate('Processing', string)
        
    def createInstance(self):
        return BrutvoegelAlgorithm() 
        
    def name(self):
        # v2 zwingt QGIS, den Cache neu zu bauen
        return 'brutvoegel_lr_algo_v2' 
        
    def displayName(self):
        return self.tr('Brutvögel_Papierrevier_LR')
        
    def group(self):
        return self.tr('Brutvogel Werkzeuge')
        
    def groupId(self):
        return 'brutvogel_tools_lr'

    def shortHelpString(self):
        return """
        <h3>Anleitung: Brutvogel Papierreviere</h3>
        <p>Dieses Werkzeug erstellt automatisiert Revierpolygone für die avifaunistische Kartierung nach fachlichen Standards.</p>
        
        <h4>Funktionsweise:</h4>
        <ul>
            <li><b>Metrische Präzision (UTM 32N):</b> Alle Punkte werden intern in UTM 32N transformiert. Die Abstände sind also immer echte Meter.</li>
            <li><b>Clustering (70m):</b> Punkte werden zusammengefasst, wenn sie näher als die Suchdistanz zueinander liegen.</li>
            <li><b>Anti-Ketten-Regel (Dynamisch):</b> Um langgezogene Polygone zu verhindern, wird die Ausdehnung begrenzt. Der Faktor bezieht sich auf die Suchdistanz.</li>
            <li><b>Brutnachweise (BN):</b> Punkte mit Hinweisen wie "Nest", "Fütter", "Brüt" werden priorisiert.</li>
            <li><b>Geometrie:</b> Konvexe Hülle mit exaktem 1,5m Puffer.</li>
            <li><b>Daten:</b> Alle Original-Attribute werden bewahrt.</li>
        </ul>
        
        <h4>Wichtige Parameter erklärt:</h4>
        <ul>
            <li><b>Suchdistanz:</b> Der Radius, in dem nach Nachbarpunkten gesucht wird (Standard: 70m).</li>
            <li><b>Anti-Ketten-Faktor:</b> Begrenzt den maximalen Durchmesser eines Clusters relativ zum Startpunkt.</li>
            <li><b>Split-Schwellenwert:</b> Ab wie vielen Punkten (ohne BN) soll ein Cluster geteilt werden? (Standard: 7).</li>
        </ul>
        """

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource('INPUT', self.tr('Eingabe Punkte'), [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterDistance('DISTANCE', self.tr('Suchdistanz (m)'), defaultValue=70.0))
        self.addParameter(QgsProcessingParameterNumber('CHAIN_FACTOR', self.tr('Anti-Ketten-Faktor'), type=QgsProcessingParameterNumber.Double, defaultValue=1.5))
        self.addParameter(QgsProcessingParameterNumber('MIN_POINTS', self.tr('Mindestanzahl Beob.'), defaultValue=2))
        self.addParameter(QgsProcessingParameterNumber('SPLIT_THRESHOLD', self.tr('Split-Schwellenwert'), defaultValue=7))
        self.addParameter(QgsProcessingParameterField('FIELD_DATE', self.tr('Datums-Feld'), parentLayerParameterName='INPUT', optional=True))
        self.addParameter(QgsProcessingParameterNumber('MIN_DAYS', self.tr('Mindest-Tage (Phänologie)'), defaultValue=10))
        self.addParameter(QgsProcessingParameterField('FIELD_ART', self.tr('Art-Name Feld'), parentLayerParameterName='INPUT'))
        self.addParameter(QgsProcessingParameterField('FIELDS_BEHAVIOR', self.tr('Verhaltens-Felder'), parentLayerParameterName='INPUT', allowMultiple=True))
        self.addParameter(QgsProcessingParameterFeatureSink('OUTPUT_POLY', self.tr('Reviere (Polygone)')))
        self.addParameter(QgsProcessingParameterFeatureSink('OUTPUT_POINT', self.tr('Zentren')))

    def split_cluster(self, features, num_clusters):
        if len(features) < num_clusters: return [features]
        sorted_features = sorted(features, key=lambda f: f['m_point'].x())
        splits = []
        chunk_size = math.ceil(len(sorted_features) / num_clusters)
        for i in range(0, len(sorted_features), chunk_size):
            chunk = sorted_features[i:i + chunk_size]
            if chunk: splits.append(chunk)
        return splits

    def parse_date(self, val):
        if isinstance(val, QDate): return val
        if isinstance(val, QDateTime): return val.date()
        s = str(val).strip()
        for f in ["yyyy-MM-dd", "dd.MM.yyyy", "dd.MM.yy"]:
            d = QDate.fromString(s[:10], f)
            if d.isValid(): return d
        return None

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, 'INPUT', context)
        dist_t = self.parameterAsDouble(parameters, 'DISTANCE', context)
        chain_f = self.parameterAsDouble(parameters, 'CHAIN_FACTOR', context)
        min_p = self.parameterAsInt(parameters, 'MIN_POINTS', context)
        split_l = self.parameterAsInt(parameters, 'SPLIT_THRESHOLD', context)
        date_f = self.parameterAsString(parameters, 'FIELD_DATE', context)
        min_d = self.parameterAsInt(parameters, 'MIN_DAYS', context)
        art_f = self.parameterAsString(parameters, 'FIELD_ART', context)
        beh_fs = self.parameterAsFields(parameters, 'FIELDS_BEHAVIOR', context)

        source_crs = source.sourceCrs()
        metric_crs = QgsCoordinateReferenceSystem('EPSG:25832') 
        to_m = QgsCoordinateTransform(source_crs, metric_crs, context.transformContext())
        to_s = QgsCoordinateTransform(metric_crs, source_crs, context.transformContext())
        max_spread = dist_t * chain_f

        MAPPING = [
            (16, "C16 - Nest mit Jungen/Fütterung", r"(\bfütter|\bjungv|\bfamili)"),
            (15, "C15 - Nest mit Eiern/brütend", r"(\bbrüt|\bei\b|\beier\b|\bgelege)"),
            (14, "C14 - Kot/Futter tragend", r"(\bgetragen|\bkotballen|\bfuttertrag)"),
            (10, "B10 - Nestbau/Nistmaterial", r"(\bnestbau|\bhöhlenbau|\bbau\b)"),
            (4,  "B4 - Dauerhafte Anwesenheit", r"(\bstationär|\bdauerhaft)"),
            (3,  "A3 - Gesang/Instrumentallaute", r"(\bsing|\bgesang|\bruf\b|\btrommel)"),
            (1,  "A1 - Beobachtung zur Brutzeit", r"(\bsichtung|\bbeobachtet)")
        ]

        art_groups = {}
        for feat in source.getFeatures():
            art = str(feat[art_f]).upper()
            g = QgsGeometry(feat.geometry())
            g.transform(to_m)
            p = g.asPoint()
            dt = self.parse_date(feat[date_f]) if date_f else None
            txt = " ".join([str(feat[f]) for f in beh_fs if feat[f] is not None]).lower()
            bp, bs = 1, "A1"
            for prio, s_txt, pat in MAPPING:
                if re.search(pat, txt): 
                    bp, bs = prio, s_txt
                    break
            art_groups.setdefault(art, []).append({'f': feat, 'm_point': p, 'd': dt, 'is_c': bp>=11, 'prio': bp, 'st': bs})

        out_fields = QgsFields()
        for f in source.fields(): out_fields.append(QgsField(f.name(), QVariant.String, len=2500))
        out_fields.append(QgsField('Status', QVariant.String, len=100))
        out_fields.append(QgsField('Beob_Anz', QVariant.Int))
        out_fields.append(QgsField('Tage_Spanne', QVariant.Int))

        (sink_poly, d_poly) = self.parameterAsSink(parameters, 'OUTPUT_POLY', context, out_fields, QgsWkbTypes.MultiPolygon, source_crs)
        (sink_pnt, d_pnt) = self.parameterAsSink(parameters, 'OUTPUT_POINT', context, out_fields, QgsWkbTypes.Point, source_crs)

        for art, feats in art_groups.items():
            used_ids = set()
            clusters = []
            for p in feats:
                if p['is_c']:
                    clusters.append({'cluster': [p], 'is_c': True})
                    used_ids.add(p['f'].id())
            for i in range(len(feats)):
                p = feats[i]
                if p['f'].id() in used_ids: continue
                curr_c = [p]; stack = [p]; seed_point = p['m_point']; used_ids.add(p['f'].id())
                while stack:
                    curr = stack.pop(); p1 = curr['m_point']
                    for j in range(len(feats)):
                        cand = feats[j]
                        if cand['f'].id() not in used_ids:
                            p2 = cand['m_point']
                            if math.sqrt(p1.sqrDist(p2)) <= dist_t and math.sqrt(seed_point.sqrDist(p2)) <= max_spread:
                                curr_c.append(cand); used_ids.add(cand['f'].id()); stack.append(cand)
                clusters.append({'cluster': curr_c, 'is_c': False})
                
            for c_obj in clusters:
                pts = c_obj['cluster']; span = 0
                if date_f:
                    ds = [x['d'] for x in pts if x['d']]
                    if len(ds) >= 2: span = min(ds).daysTo(max(ds))
                if not (c_obj['is_c'] or len(pts) >= min_p): continue
                s_count = 3 if (not c_obj['is_c'] and len(pts) >= (split_l * 1.5)) else (2 if (not c_obj['is_c'] and len(pts) >= split_l) else 1)
                sub_clusters = self.split_cluster(pts, s_count)
                for sub in sub_clusters:
                    if not sub: continue
                    best = max(sub, key=lambda x: x['prio']); final_st = best['st']
                    if span >= min_d and best['prio'] < 4: final_st = "B4 - Dauerhafte Anwesenheit (Zeit-Check)"
                    attr = []
                    for f in source.fields():
                        vals = set()
                        for x in sub:
                            val = x['f'][f.name()]
                            if val is not None:
                                s_val = val.toString('dd.MM.yyyy') if isinstance(val, (QDate, QDateTime)) else str(val).strip()
                                if s_val and s_val.lower() != 'null': vals.add(s_val)
                        attr.append(", ".join(sorted(list(vals)))[:2500])
                    attr.extend([final_st, len(sub), span])
                    m_pts = QgsGeometry.fromMultiPointXY([x['m_point'] for x in sub])
                    poly_geom = m_pts.convexHull().buffer(1.5, 5) if len(sub)>1 else m_pts.buffer(1.5, 5)
                    poly_geom.transform(to_s)
                    fp = QgsFeature(out_fields); fp.setAttributes(attr); fp.setGeometry(poly_geom); sink_poly.addFeature(fp)
                    fpt = QgsFeature(out_fields); fpt.setAttributes(attr); fpt.setGeometry(poly_geom.centroid()); sink_pnt.addFeature(fpt)
        return {'OUTPUT_POLY': d_poly, 'OUTPUT_POINT': d_pnt}
