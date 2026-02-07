"""
Build NY Density Map - Preprocessing Script
=============================================
Converts ZIP KML + Census Tract shapefile boundaries into GeoJSON,
joins density data, and injects into ny_density_map.html.

Usage:
    py scripts/build_density_map.py

Dependencies: pyshp (pip install pyshp), requests
"""

import csv
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

# Optional imports - install if missing
try:
    import shapefile
except ImportError:
    print("Installing pyshp...")
    os.system(f"{sys.executable} -m pip install pyshp")
    import shapefile

try:
    import requests
except ImportError:
    print("Installing requests...")
    os.system(f"{sys.executable} -m pip install requests")
    import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
KML_PATH = os.path.join(BASE_DIR, "new-york-zip-codes.kml")
HTML_PATH = os.path.join(BASE_DIR, "ny_density_map.html")

TRACT_SHP_URL = "https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_36_tract_500k.zip"
TRACT_SHP_ZIP = os.path.join(DATA_DIR, "cb_2022_36_tract_500k.zip")

COUNTY_DENSITY_CSV = os.path.join(DATA_DIR, "ny_county_density.csv")
ZIP_DENSITY_CSV = os.path.join(DATA_DIR, "ny_zip_density.csv")
TRACT_DENSITY_CSV = os.path.join(DATA_DIR, "ny_tract_density.csv")

CONGRESS_GEOJSON_PATH = os.path.join(
    os.path.expanduser("~"), "Downloads",
    "NYS_Congressional_Districts_1248143431698889131.geojson",
)

COORD_PRECISION = 4  # ~11m accuracy

# NY-specific public sector union density rates (from state_govt_level_density)
NY_FED_RATE = 48.57
NY_STATE_RATE = 53.37
NY_LOCAL_RATE = 73.33


def calc_public_density(row):
    """Calculate true public sector union density from govt share columns."""
    fed = float(row.get("federal_share") or 0)
    st = float(row.get("state_share") or 0)
    loc = float(row.get("local_share") or 0)
    govt = float(row.get("govt_class_total") or 0)
    if govt < 0.01:
        return 0.0
    contrib = fed * NY_FED_RATE + st * NY_STATE_RATE + loc * NY_LOCAL_RATE
    return round(contrib / govt, 1)


def round_coords(coords):
    """Round coordinate list to COORD_PRECISION decimal places."""
    return [[round(c[0], COORD_PRECISION), round(c[1], COORD_PRECISION)] for c in coords]


# =============================================================
# STEP 0: Build County Data from CSV
# =============================================================

def build_county_data():
    """Build COUNTY_DATA array from ny_county_density.csv."""
    print("Building county data from CSV...")
    counties = []
    with open(COUNTY_DENSITY_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            counties.append({
                "fips": row["fips"].strip(),
                "name": row["name"].strip().strip('"'),
                "total": round(float(row["estimated_total_density"] or 0), 1),
                "private": round(float(row["estimated_private_density"] or 0), 1),
                "public": calc_public_density(row),
                "federal": round(float(row["estimated_federal_density"] or 0), 2),
                "state_d": round(float(row["estimated_state_density"] or 0), 2),
                "local": round(float(row["estimated_local_density"] or 0), 2),
            })
    print(f"  Loaded {len(counties)} counties")
    return counties


def build_zip_data():
    """Build ZIP_DATA array from ny_zip_density.csv."""
    print("Building ZIP data from CSV...")
    zips = []
    with open(ZIP_DENSITY_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            zips.append({
                "z": row["fips"].strip(),
                "n": row.get("name", "").strip().strip('"'),
                "t": round(float(row["estimated_total_density"] or 0), 1),
                "p": round(float(row["estimated_private_density"] or 0), 1),
                "u": calc_public_density(row),
            })
    print(f"  Loaded {len(zips)} ZIP codes")
    return zips


def build_tract_data():
    """Build TRACT_DATA array from ny_tract_density.csv."""
    print("Building tract data from CSV...")
    tracts = []
    with open(TRACT_DENSITY_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fips = row["fips"].strip()
            name_raw = row.get("name", "").strip().strip('"')
            # Extract tract number and county from name like "CT000100, Albany County, NY"
            parts = name_raw.split(",")
            tract_name = parts[0].strip() if parts else fips
            county_name = parts[1].strip().replace(" County", "") if len(parts) > 1 else ""
            tracts.append({
                "g": fips,
                "n": tract_name,
                "c": county_name,
                "t": round(float(row["estimated_total_density"] or 0), 1),
                "p": round(float(row["estimated_private_density"] or 0), 1),
                "u": calc_public_density(row),
            })
    print(f"  Loaded {len(tracts)} census tracts")
    return tracts


# =============================================================
# STEP 1: Parse ZIP KML -> GeoJSON
# =============================================================

def parse_kml_zips():
    """Parse new-york-zip-codes.kml into GeoJSON FeatureCollection."""
    print("Parsing ZIP KML...")
    tree = ET.parse(KML_PATH)
    root = tree.getroot()
    ns = {"kml": "http://www.opengis.net/kml/2.2"}

    # Load density data
    zip_density = {}
    zip_names = {}
    with open(ZIP_DENSITY_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fips = row["fips"].strip()
            zip_density[fips] = {
                "t": round(float(row["estimated_total_density"] or 0), 1),
                "p": round(float(row["estimated_private_density"] or 0), 1),
                "u": calc_public_density(row),
            }
            zip_names[fips] = row.get("name", "").strip()

    features = []
    placemarks = root.findall(".//kml:Placemark", ns)

    for pm in placemarks:
        name_el = pm.find("kml:name", ns)
        if name_el is None:
            continue
        zip_code = name_el.text.strip()

        # Check for MultiGeometry or single Polygon
        multi = pm.find("kml:MultiGeometry", ns)
        if multi is not None:
            polygons_els = multi.findall("kml:Polygon", ns)
        else:
            poly = pm.find("kml:Polygon", ns)
            polygons_els = [poly] if poly is not None else []

        if not polygons_els:
            continue

        geom_polygons = []
        for poly_el in polygons_els:
            outer_el = poly_el.find("kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", ns)
            if outer_el is None:
                continue

            outer_ring = parse_kml_coordinates(outer_el.text)
            rings = [round_coords(outer_ring)]

            # Inner boundaries (holes)
            for inner_el in poly_el.findall("kml:innerBoundaryIs/kml:LinearRing/kml:coordinates", ns):
                inner_ring = parse_kml_coordinates(inner_el.text)
                rings.append(round_coords(inner_ring))

            geom_polygons.append(rings)

        if not geom_polygons:
            continue

        # Determine geometry type
        if len(geom_polygons) == 1:
            geometry = {"type": "Polygon", "coordinates": geom_polygons[0]}
        else:
            geometry = {"type": "MultiPolygon", "coordinates": geom_polygons}

        # Get density data
        density = zip_density.get(zip_code, {"t": 0, "p": 0, "u": 0})
        loc_name = zip_names.get(zip_code, "")

        feature = {
            "type": "Feature",
            "properties": {
                "z": zip_code,
                "n": loc_name,
                "t": density["t"],
                "p": density["p"],
                "u": density["u"],
            },
            "geometry": geometry,
        }
        features.append(feature)

    print(f"  Parsed {len(features)} ZIP polygons, {len(zip_density)} density records")
    matched = sum(1 for f in features if f["properties"]["t"] > 0)
    print(f"  Matched to density: {matched}/{len(features)}")

    return {"type": "FeatureCollection", "features": features}


def parse_kml_coordinates(text):
    """Parse KML coordinate string 'lon,lat,alt lon,lat,alt ...' into [[lon,lat], ...]."""
    coords = []
    for pair in text.strip().split():
        parts = pair.split(",")
        if len(parts) >= 2:
            lon, lat = float(parts[0]), float(parts[1])
            coords.append([lon, lat])
    return coords


# =============================================================
# STEP 2: Download & Parse Census Tract Shapefile -> GeoJSON
# =============================================================

def download_tract_shapefile():
    """Download census tract shapefile if not already present."""
    if os.path.exists(TRACT_SHP_ZIP):
        print(f"  Tract shapefile already downloaded: {TRACT_SHP_ZIP}")
        return

    print(f"  Downloading tract shapefile from Census Bureau...")
    resp = requests.get(TRACT_SHP_URL, stream=True)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(TRACT_SHP_ZIP, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded * 100 // total
                print(f"\r  Downloaded: {downloaded:,} / {total:,} bytes ({pct}%)", end="")
    print()


def parse_tract_shapefile():
    """Parse census tract shapefile into GeoJSON FeatureCollection."""
    print("Parsing Census Tract shapefile...")
    download_tract_shapefile()

    # Load density data
    tract_density = {}
    with open(TRACT_DENSITY_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            geoid = row["fips"].strip()
            name = row.get("name", "").strip()
            tract_density[geoid] = {
                "n": name,
                "t": round(float(row["estimated_total_density"] or 0), 1),
                "p": round(float(row["estimated_private_density"] or 0), 1),
                "u": calc_public_density(row),
            }

    # Extract and read shapefile from ZIP
    with zipfile.ZipFile(TRACT_SHP_ZIP, "r") as zf:
        # Find the .shp file
        shp_name = None
        for name in zf.namelist():
            if name.endswith(".shp"):
                shp_name = name
                break

        if not shp_name:
            raise FileNotFoundError("No .shp file found in ZIP")

        # Extract required files to memory
        base_name = shp_name[:-4]
        shp_data = io.BytesIO(zf.read(base_name + ".shp"))
        shx_data = io.BytesIO(zf.read(base_name + ".shx"))
        dbf_data = io.BytesIO(zf.read(base_name + ".dbf"))

    sf = shapefile.Reader(shp=shp_data, shx=shx_data, dbf=dbf_data)

    # Find field indices
    fields = [f[0] for f in sf.fields[1:]]  # Skip DeletionFlag
    geoid_idx = fields.index("GEOID") if "GEOID" in fields else fields.index("AFFGEOID")
    name_idx = fields.index("NAME") if "NAME" in fields else -1
    county_idx = fields.index("COUNTYFP") if "COUNTYFP" in fields else -1

    # County FIPS to name mapping for NY
    county_names = {
        "001": "Albany", "003": "Allegany", "005": "Bronx", "007": "Broome",
        "009": "Cattaraugus", "011": "Cayuga", "013": "Chautauqua", "015": "Chemung",
        "017": "Chenango", "019": "Clinton", "021": "Columbia", "023": "Cortland",
        "025": "Delaware", "027": "Dutchess", "029": "Erie", "031": "Essex",
        "033": "Franklin", "035": "Fulton", "037": "Genesee", "039": "Greene",
        "041": "Hamilton", "043": "Herkimer", "045": "Jefferson", "047": "Kings",
        "049": "Lewis", "051": "Livingston", "053": "Madison", "055": "Monroe",
        "057": "Montgomery", "059": "Nassau", "061": "New York", "063": "Niagara",
        "065": "Oneida", "067": "Onondaga", "069": "Ontario", "071": "Orange",
        "073": "Orleans", "075": "Oswego", "077": "Otsego", "079": "Putnam",
        "081": "Queens", "083": "Rensselaer", "085": "Richmond", "087": "Rockland",
        "089": "St. Lawrence", "091": "Saratoga", "093": "Schenectady",
        "095": "Schoharie", "097": "Schuyler", "099": "Seneca", "101": "Steuben",
        "103": "Suffolk", "105": "Sullivan", "107": "Tioga", "109": "Tompkins",
        "111": "Ulster", "113": "Warren", "115": "Washington", "117": "Wayne",
        "119": "Westchester", "121": "Wyoming", "123": "Yates",
    }

    features = []
    for sr in sf.iterShapeRecords():
        geoid = sr.record[geoid_idx]
        tract_name = sr.record[name_idx] if name_idx >= 0 else ""
        county_fp = sr.record[county_idx] if county_idx >= 0 else geoid[2:5]
        county_name = county_names.get(county_fp, county_fp)

        # Convert shapefile geometry to GeoJSON
        geom = sr.shape.__geo_interface__
        # Round coordinates
        geom = round_geometry(geom)

        # Look up density
        density = tract_density.get(geoid, {"n": "", "t": 0, "p": 0, "u": 0})

        feature = {
            "type": "Feature",
            "properties": {
                "g": geoid,
                "n": f"Tract {tract_name}",
                "c": county_name,
                "t": density["t"],
                "p": density["p"],
                "u": density["u"],
            },
            "geometry": geom,
        }
        features.append(feature)

    print(f"  Parsed {len(features)} tract polygons, {len(tract_density)} density records")
    matched = sum(1 for f in features if f["properties"]["t"] > 0)
    print(f"  Matched to density: {matched}/{len(features)}")

    return {"type": "FeatureCollection", "features": features}


def round_geometry(geom):
    """Recursively round coordinates in a GeoJSON geometry to COORD_PRECISION."""
    geom_type = geom["type"]
    coords = geom["coordinates"]

    if geom_type == "Polygon":
        geom["coordinates"] = [round_coords(ring) for ring in coords]
    elif geom_type == "MultiPolygon":
        geom["coordinates"] = [[round_coords(ring) for ring in poly] for poly in coords]
    elif geom_type == "Point":
        geom["coordinates"] = [round(c, COORD_PRECISION) for c in coords]

    return geom


# =============================================================
# STEP 2B: Build Congressional District Data
# =============================================================

def polygon_area(ring):
    """Compute signed area of a polygon ring (Shoelace formula)."""
    n = len(ring)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += ring[i][0] * ring[j][1]
        area -= ring[j][0] * ring[i][1]
    return abs(area) / 2.0


def point_in_polygon(px, py, polygon_rings):
    """Ray-casting point-in-polygon test. First ring is outer, rest are holes."""
    inside = False
    for ring_idx, ring in enumerate(polygon_rings):
        n = len(ring)
        j = n - 1
        for i in range(n):
            yi, yj = ring[i][1], ring[j][1]
            xi, xj = ring[i][0], ring[j][0]
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        # After outer ring, if point is outside outer, bail early
        if ring_idx == 0 and not inside:
            return False
    return inside


def point_in_multipolygon(px, py, geom):
    """Test if point is inside a GeoJSON Polygon or MultiPolygon."""
    if geom["type"] == "Polygon":
        return point_in_polygon(px, py, geom["coordinates"])
    elif geom["type"] == "MultiPolygon":
        for poly_rings in geom["coordinates"]:
            if point_in_polygon(px, py, poly_rings):
                return True
    return False


def bbox_of_geom(geom):
    """Compute bounding box [min_lon, min_lat, max_lon, max_lat] of a geometry."""
    all_coords = []
    if geom["type"] == "Polygon":
        for ring in geom["coordinates"]:
            all_coords.extend(ring)
    elif geom["type"] == "MultiPolygon":
        for poly in geom["coordinates"]:
            for ring in poly:
                all_coords.extend(ring)
    if not all_coords:
        return None
    lons = [c[0] for c in all_coords]
    lats = [c[1] for c in all_coords]
    return [min(lons), min(lats), max(lons), max(lats)]


def centroid_of_bbox(bbox):
    """Return center point of a bounding box."""
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def simplify_ring(ring, tolerance=0.003):
    """Douglas-Peucker line simplification."""
    if len(ring) <= 3:
        return ring

    def _dp(points, start, end, tol):
        max_dist = 0
        max_idx = start
        for i in range(start + 1, end):
            d = _point_line_dist(points[i], points[start], points[end])
            if d > max_dist:
                max_dist = d
                max_idx = i
        if max_dist > tol:
            left = _dp(points, start, max_idx, tol)
            right = _dp(points, max_idx, end, tol)
            return left[:-1] + right
        else:
            return [points[start], points[end]]

    def _point_line_dist(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if dx == 0 and dy == 0:
            return ((p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2) ** 0.5
        t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
        proj_x = a[0] + t * dx
        proj_y = a[1] + t * dy
        return ((p[0] - proj_x) ** 2 + (p[1] - proj_y) ** 2) ** 0.5

    sys.setrecursionlimit(max(sys.getrecursionlimit(), len(ring) * 2))
    simplified = _dp(ring, 0, len(ring) - 1, tolerance)
    # Ensure closed ring
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    return simplified


def simplify_geometry(geom, tolerance=0.003):
    """Simplify a GeoJSON Polygon or MultiPolygon geometry."""
    if geom["type"] == "Polygon":
        geom["coordinates"] = [simplify_ring(ring, tolerance) for ring in geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        geom["coordinates"] = [
            [simplify_ring(ring, tolerance) for ring in poly]
            for poly in geom["coordinates"]
        ]
    return geom


def build_congress_data(tract_data):
    """Build congressional district GeoJSON with density from tract centroids."""
    print("Building Congressional District data...")

    if not os.path.exists(CONGRESS_GEOJSON_PATH):
        print(f"  WARNING: Congressional district file not found: {CONGRESS_GEOJSON_PATH}")
        return None

    with open(CONGRESS_GEOJSON_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    print(f"  Loaded {len(raw['features'])} congressional districts")

    # Simplify district geometries and compute bboxes
    districts = []
    for feat in raw["features"]:
        props = feat["properties"]
        geom = feat["geometry"]

        # Simplify coordinates (Douglas-Peucker then round)
        geom = simplify_geometry(geom, tolerance=0.003)
        geom = round_geometry(geom)

        # Filter tiny island polygons for MultiPolygon
        if geom["type"] == "MultiPolygon":
            filtered = [poly for poly in geom["coordinates"] if polygon_area(poly[0]) >= 0.001]
            if filtered:
                if len(filtered) == 1:
                    geom = {"type": "Polygon", "coordinates": filtered[0]}
                else:
                    geom["coordinates"] = filtered

        bbox = bbox_of_geom(geom)
        party = props.get("Party", "")
        party_initial = "D" if "democrat" in party.lower() else "R" if "republican" in party.lower() else "?"

        districts.append({
            "props": {
                "d": props.get("District", 0),
                "n": props.get("Name", ""),
                "p": party_initial,
            },
            "geom": geom,
            "bbox": bbox,
            "tracts": [],  # Will collect tract densities
        })

    # Build tract centroids from tract_data + tract shapefile geometry
    # We need tract geometries for centroids - read from shapefile
    print("  Computing tract centroids for district assignment...")
    tract_centroids = []
    tract_lookup = {t["g"]: t for t in tract_data}

    # Read tract shapefile for geometry centroids
    with zipfile.ZipFile(TRACT_SHP_ZIP, "r") as zf:
        shp_name = None
        for name in zf.namelist():
            if name.endswith(".shp"):
                shp_name = name
                break
        base_name = shp_name[:-4]
        shp_data = io.BytesIO(zf.read(base_name + ".shp"))
        shx_data = io.BytesIO(zf.read(base_name + ".shx"))
        dbf_data = io.BytesIO(zf.read(base_name + ".dbf"))

    sf = shapefile.Reader(shp=shp_data, shx=shx_data, dbf=dbf_data)
    fields = [f[0] for f in sf.fields[1:]]
    geoid_idx = fields.index("GEOID") if "GEOID" in fields else fields.index("AFFGEOID")

    for sr in sf.iterShapeRecords():
        geoid = sr.record[geoid_idx]
        if geoid not in tract_lookup:
            continue
        geom = sr.shape.__geo_interface__
        bbox = bbox_of_geom(geom)
        if bbox is None:
            continue
        cx, cy = centroid_of_bbox(bbox)
        td = tract_lookup[geoid]
        tract_centroids.append({
            "lon": cx, "lat": cy,
            "t": td["t"], "p": td["p"], "u": td["u"],
        })

    print(f"  {len(tract_centroids)} tract centroids computed")

    # Assign tracts to districts via point-in-polygon
    assigned = 0
    for tc in tract_centroids:
        px, py = tc["lon"], tc["lat"]
        for dist in districts:
            bb = dist["bbox"]
            if bb is None:
                continue
            # Bbox pre-filter
            if px < bb[0] or px > bb[2] or py < bb[1] or py > bb[3]:
                continue
            if point_in_multipolygon(px, py, dist["geom"]):
                dist["tracts"].append(tc)
                assigned += 1
                break

    print(f"  Assigned {assigned}/{len(tract_centroids)} tracts to districts")

    # Build output GeoJSON
    features = []
    for dist in districts:
        tracts = dist["tracts"]
        tc = len(tracts)
        if tc > 0:
            avg_t = round(sum(t["t"] for t in tracts) / tc, 1)
            avg_p = round(sum(t["p"] for t in tracts) / tc, 1)
            avg_u = round(sum(t["u"] for t in tracts) / tc, 1)
        else:
            avg_t = avg_p = avg_u = 0

        features.append({
            "type": "Feature",
            "properties": {
                "d": dist["props"]["d"],
                "n": dist["props"]["n"],
                "p": dist["props"]["p"],
                "t": avg_t,
                "pr": avg_p,
                "pu": avg_u,
                "tc": tc,
            },
            "geometry": dist["geom"],
        })

    congress_geojson = {"type": "FeatureCollection", "features": features}
    csize = len(json.dumps(congress_geojson, separators=(",", ":")))
    print(f"  Congress GeoJSON size: {csize:,} bytes ({csize / 1024:.0f} KB)")

    return congress_geojson


# =============================================================
# STEP 3: Optimize & Inject into HTML
# =============================================================

def geojson_to_js(var_name, geojson):
    """Convert GeoJSON to compact JavaScript variable assignment."""
    compact = json.dumps(geojson, separators=(",", ":"))
    return f"const {var_name} = {compact};"


def inject_into_html(county_data, zip_data, tract_data, zip_geojson, tract_geojson, congress_geojson=None):
    """Replace data blocks in HTML with fresh CSV data and GeoJSON."""
    print("Injecting data into HTML...")

    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. Replace COUNTY_DATA
    county_js = json.dumps(county_data, separators=(",", ":"))
    html = re.sub(
        r'const COUNTY_DATA = \[.*?\];',
        f'const COUNTY_DATA = {county_js};',
        html,
        flags=re.DOTALL,
    )

    # 2. Compute and update header stats from county data
    avg_total = sum(c["total"] for c in county_data) / len(county_data)
    avg_private = sum(c["private"] for c in county_data) / len(county_data)
    avg_public = sum(c["public"] for c in county_data) / len(county_data)
    # Update the stat-pill values
    html = re.sub(r'(<div class="value" id="hdr-total">)[\d.]+%', rf'\g<1>{avg_total:.1f}%', html)
    html = re.sub(r'(<div class="value" style="color:#60a5fa" id="hdr-priv">)[\d.]+%', rf'\g<1>{avg_private:.1f}%', html)
    html = re.sub(r'(<div class="value" style="color:#34d399" id="hdr-pub">)[\d.]+%', rf'\g<1>{avg_public:.1f}%', html)
    # Update summary card defaults
    html = re.sub(r'(<div class="sc-val" id="sc-total">)[\d.]+%', rf'\g<1>{avg_total:.1f}%', html)
    html = re.sub(r'(<div class="sc-val" id="sc-private">)[\d.]+%', rf'\g<1>{avg_private:.1f}%', html)
    html = re.sub(r'(<div class="sc-val" id="sc-public">)[\d.]+%', rf'\g<1>{avg_public:.1f}%', html)

    # 3. Generate JS variable assignments for GeoJSON
    zip_geo_js = geojson_to_js("ZIP_GEOJSON", zip_geojson)
    tract_geo_js = geojson_to_js("TRACT_GEOJSON", tract_geojson)

    # 4. Replace zip-data-script block (also embed ZIP_DATA for the table)
    zip_data_js = f"const ZIP_DATA_INIT = {json.dumps(zip_data, separators=(',', ':'))};"
    html = re.sub(
        r'<script id="zip-data-script">.*?</script>',
        f'<script id="zip-data-script">\n{zip_geo_js}\n{zip_data_js}\nZIP_DATA = ZIP_DATA_INIT;\n</script>',
        html,
        flags=re.DOTALL,
    )

    # 5. Replace tract-data-script block (also embed TRACT_DATA for the table)
    tract_data_js = f"const TRACT_DATA_INIT = {json.dumps(tract_data, separators=(',', ':'))};"
    html = re.sub(
        r'<script id="tract-data-script">.*?</script>',
        f'<script id="tract-data-script">\n{tract_geo_js}\n{tract_data_js}\nTRACT_DATA = TRACT_DATA_INIT;\n</script>',
        html,
        flags=re.DOTALL,
    )

    # 6. Inject congressional district GeoJSON
    if congress_geojson:
        congress_js = geojson_to_js("CONGRESS_GEOJSON", congress_geojson)
        congress_block = f'<script id="congress-data-script">\n{congress_js}\n</script>'
        # Replace existing or insert before </body>
        if '<script id="congress-data-script">' in html:
            html = re.sub(
                r'<script id="congress-data-script">.*?</script>',
                congress_block,
                html,
                flags=re.DOTALL,
            )
        else:
            html = html.replace("</body>", f"{congress_block}\n</body>")

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    file_size = os.path.getsize(HTML_PATH)
    print(f"  HTML updated: {file_size:,} bytes ({file_size / 1024 / 1024:.1f} MB)")


def main():
    print("=" * 60)
    print("Building NY Density Map - GeoJSON Injection")
    print("=" * 60)

    # Step 0: Build data arrays from CSVs
    county_data = build_county_data()
    zip_data = build_zip_data()
    tract_data = build_tract_data()

    # Step 1: ZIP boundaries from KML
    zip_geojson = parse_kml_zips()
    zip_size = len(json.dumps(zip_geojson, separators=(",", ":")))
    print(f"  ZIP GeoJSON size: {zip_size:,} bytes ({zip_size / 1024 / 1024:.1f} MB)")

    # Step 2: Tract boundaries from Census shapefile
    tract_geojson = parse_tract_shapefile()
    tract_size = len(json.dumps(tract_geojson, separators=(",", ":")))
    print(f"  Tract GeoJSON size: {tract_size:,} bytes ({tract_size / 1024 / 1024:.1f} MB)")

    # Step 2B: Congressional districts with tract-based density
    congress_geojson = build_congress_data(tract_data)

    # Step 3: Inject into HTML
    inject_into_html(county_data, zip_data, tract_data, zip_geojson, tract_geojson, congress_geojson)

    print("\nDone! Open ny_density_map.html in a browser to verify.")


if __name__ == "__main__":
    main()
