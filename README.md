# Zoning Violation Detection Tool

This project detects illegal building constructions by analyzing their height and boundary placement using zoning policies and geospatial data. It uses Python and open-source GIS tools to automate the detection and visualization of zoning violations.

## 🔍 Features
- Calculates building heights from DSM and DTM elevation data
- Checks for height limit and setback (boundary) violations based on zoning policy
- Categorizes violations into Height, Boundary, and Both
- Displays results on an interactive, color-coded Folium map with a custom legend

## 🛠 Technologies Used
- Python
- GeoPandas
- Rasterio
- Folium
- Shapely
- NumPy
- OpenStreetMap (building footprints)

