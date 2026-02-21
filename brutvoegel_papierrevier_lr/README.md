# Brutvögel_Papierrevier_LR

A QGIS 3 plugin for automated territory mapping of breeding birds (Papierrevier-Methode) based on professional standards (Südbeck classification).

## Features
* **Status Recognition:** Automatically assigns the highest breeding status (A1 to C16) using regex word boundaries.
* **Time Criterion:** Upgrades territories to "probable breeding" (B4) if the temporal distance between the first and last observation exceeds a threshold (e.g., 10 days).
* **Spatial Clustering:** Single-linkage metric clustering with a dynamic anti-chain rule to prevent unnaturally stretched territories.
* **Smart Splitting:** Divides massive clusters lacking a confirmed breeding status into multiple logical territories.
* **Geometry Generation:** Creates convex hulls with a precise 1.5m buffer for polygons and calculates true centroids.

## Installation
Currently available via manual ZIP install or the QGIS Plugin Repository.
