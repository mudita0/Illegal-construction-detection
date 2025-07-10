import geopandas as gpd
import rasterio
from rasterio.mask import mask
from rasterio.warp import reproject, Resampling
import json
from shapely.geometry import Polygon
import numpy as np
import folium

# === STEP 1: Load Zoning Data ===
zones = gpd.read_file("HomogenousSubZones/HomogenousSubZones.shp")
zones["Max Height"] = 10.5     # Replace with actual values if available
zones["Setback"] = 5.0         # Replace with actual setback values if needed

# === STEP 2: Load DSM and DTM ===
dsm = rasterio.open("P5_PAN_CD_N30_000_E076_000_DEM_30m.tif")
dtm = rasterio.open("n30_e076_1arc_v3.tif")

# Reproject zones to DSM CRS
zones = zones.to_crs(dsm.crs)

# === STEP 3: Clip DSM and DTM to zoning areas ===
dsm_clip, dsm_transform = mask(dsm, zones.geometry, crop=True)
dsm_array = dsm_clip[0].astype(float)

dtm_clip, _ = mask(dtm, zones.geometry, crop=True)
dtm_array = dtm_clip[0].astype(float)

# === STEP 4: Resample DTM to match DSM ===
resampled_dtm = np.empty_like(dsm_array)
reproject(
    dtm_array, resampled_dtm,
    src_transform=dtm.transform,
    src_crs=dtm.crs,
    dst_transform=dsm_transform,
    dst_crs=dsm.crs,
    dst_resolution=dsm.res,
    resampling=Resampling.bilinear
)

# === STEP 5: Compute Height Map ===
height_map = dsm_array - resampled_dtm
height_map[height_map < 0] = 0  # Clean negative values

# === STEP 6: Load OSM Building Footprints ===
with open("export.json") as f:
    data = json.load(f)

# Reconstruct polygons
features = []
node_map = {el["id"]: (el["lon"], el["lat"]) for el in data["elements"] if el["type"] == "node"}

for el in data["elements"]:
    if el["type"] == "way" and "building" in el.get("tags", {}):
        nodes = el["nodes"]
        coords = [node_map[nid] for nid in nodes if nid in node_map]
        if len(coords) >= 3:
            geom = Polygon(coords)
            tags = el["tags"]
            levels = tags.get("building:levels")
            height = tags.get("height")
            est_height = float(height) if height else (int(levels) * 3 if levels else None)
            features.append({
                "geometry": geom,
                "height": est_height,
                "name": tags.get("name", ""),
                "levels": levels
            })

buildings_gdf = gpd.GeoDataFrame(features, crs="EPSG:4326")
buildings_gdf = buildings_gdf.to_crs(dsm.crs)

# === STEP 7: Spatial Join with Zoning Polygons ===
buildings_within = gpd.sjoin(buildings_gdf, zones, predicate="within", how="inner")

# === STEP 8: Create Buildable Area (setback buffer) ===
# Project zones to UTM CRS for accurate buffering
zones_projected = zones.to_crs(epsg=32643)  # Use UTM zone matching your area

# Apply buffer to create buildable area (accounting for setback)
zones_projected["buildable_area"] = zones_projected.geometry.buffer(-zones_projected["Setback"])
zones_projected["buildable_area"] = zones_projected["buildable_area"].buffer(0)

# Bring it back to DSM CRS
zones["buildable_area"] = zones_projected["buildable_area"].to_crs(dsm.crs)


# === STEP 9: Check Boundary Violation ===
boundary_violations = []
for _, building in buildings_within.iterrows():
    zone = zones.loc[zones.index == building["index_right"]].iloc[0]
    in_buildable = building.geometry.within(zone["buildable_area"])
    boundary_violations.append(not in_buildable)

buildings_within["boundary_violation"] = boundary_violations

# === STEP 10: Check Height Violation ===
buildings_within["violation"] = buildings_within["height"] > buildings_within["Max Height"]

# === STEP 11: Label Violation Type ===
def classify_violation(row):
    if row["violation"] and row["boundary_violation"]:
        return "Both"
    elif row["violation"]:
        return "Height"
    elif row["boundary_violation"]:
        return "Boundary"
    else:
        return "None"

buildings_within["violation_type"] = buildings_within.apply(classify_violation, axis=1)

# === STEP 12: Visualize on Map ===
m = folium.Map(location=[30.741, 76.768], zoom_start=14)

color_map = {
    "Height": "yellow",
    "Boundary": "orange",
    "Both": "red"
}

for _, row in buildings_within.iterrows():
    if row["violation_type"] == "None":
        continue
    centroid = row.geometry.centroid
    folium.CircleMarker(
        location=[centroid.y, centroid.x],
        radius=6,
        color=color_map[row["violation_type"]],
        fill=True,
        fill_opacity=0.8,
        popup=f"{row.get('name', 'Unnamed')}<br>Type: {row['violation_type']}<br>Height: {row['height']}m"
    ).add_to(m)

from folium import Element

legend_html = """
<div style="
     position: fixed;
     bottom: 30px;
     left: 30px;
     z-index: 9999;
     background-color: white;
     border:2px solid grey;
     padding: 10px;
     font-size: 14px;
     border-radius: 8px;
     box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
">
<b>Violation Legend</b><br>
<span style="background-color:yellow; border-radius:50%; display:inline-block; width:10px; height:10px;"></span>
&nbsp; Height Violation<br>
<span style="background-color:orange; border-radius:50%; display:inline-block; width:10px; height:10px;"></span>
&nbsp; Boundary Violation<br>
<span style="background-color:red; border-radius:50%; display:inline-block; width:10px; height:10px;"></span>
&nbsp; Both Violations
</div>
"""

m.get_root().html.add_child(Element(legend_html))

m.save("zoning_violations_map.html")
print("Map saved as zoning_violations_map.html")
