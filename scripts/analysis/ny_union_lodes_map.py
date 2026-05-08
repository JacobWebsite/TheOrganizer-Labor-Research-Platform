"""
NY Union Employer LODES Commute-Shed Mapping — One-Off Analysis

Picks 10 NY union employers (5 NYC / 5 elsewhere, all >1000 employees), then
for each computes a tract-level choropleth of "where industry-matched workers
live" using LODES 2022 OD flows apportioned by WAC CNS share in the workplace
tract.

Modes:
  --select-only    Run selection, write data/employer_picks.csv, stop.
  --run            Read the picks CSV, compute commute sheds, render maps,
                   write CSVs + verification log.
  --all            Do both in one go (skips the approval pause).

See C:/Users/jakew/.claude/plans/i-want-to-pick-vast-willow.md for the plan.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

import folium
import branca.colormap as cm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from db_config import get_connection  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "analysis" / "demographics_comparison"))
from config import NAICS_TO_CNS  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="geopandas")

GEO_ROOT = PROJECT_ROOT / "New Data sources 2_27" / "tiger_2022_ny"
DEFAULT_OUTDIR = PROJECT_ROOT / "analysis" / "ny_union_lodes_map_2026_04"

NYC_COUNTY_FIPS = {"36005", "36047", "36061", "36081", "36085"}
NYC_COUNTY_NAMES = {
    "36005": "Bronx",
    "36047": "Brooklyn",
    "36061": "Manhattan",
    "36081": "Queens",
    "36085": "Staten Island",
}


# ---------------------------------------------------------------------------
# Shapefile loading
# ---------------------------------------------------------------------------

@dataclass
class Shapes:
    tracts: gpd.GeoDataFrame
    counties: gpd.GeoDataFrame
    cousubs: gpd.GeoDataFrame
    ntas: gpd.GeoDataFrame


def load_shapes() -> Shapes:
    print("Loading shapefiles...")
    tracts = gpd.read_file(GEO_ROOT / "tl_2022_36_tract" / "tl_2022_36_tract.shp")
    tracts = tracts.to_crs("EPSG:4326")
    tracts["county_fips"] = tracts["STATEFP"].astype(str) + tracts["COUNTYFP"].astype(str)

    all_county = gpd.read_file(GEO_ROOT / "tl_2022_36_county" / "tl_2022_us_county.shp")
    counties = all_county.query("STATEFP == '36'").to_crs("EPSG:4326").reset_index(drop=True)

    cousubs = gpd.read_file(GEO_ROOT / "tl_2022_36_cousub" / "tl_2022_36_cousub.shp")
    cousubs = cousubs.to_crs("EPSG:4326")

    ntas = gpd.read_file(GEO_ROOT / "nynta2020.geojson").to_crs("EPSG:4326")

    print(f"  tracts: {len(tracts):,}   counties: {len(counties):,}   "
          f"cousubs: {len(cousubs):,}   NTAs: {len(ntas):,}")
    return Shapes(tracts=tracts, counties=counties, cousubs=cousubs, ntas=ntas)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

SELECTION_SQL = """
SELECT
    f.employer_id                AS f7_employer_id,
    f.employer_name,
    f.street                     AS f7_street,
    f.city                       AS f7_city,
    f.zip                        AS f7_zip,
    f.latitude                   AS f7_lat,
    f.longitude                  AS f7_lon,
    f.naics                      AS f7_naics,
    f.naics_detailed             AS f7_naics_detailed,
    f.latest_unit_size,
    f.latest_union_name          AS parent_union,
    cw.mergent_duns,
    m.employees_site,
    m.employees_all_sites,
    m.naics_primary              AS mergent_naics6,
    m.latitude                   AS mergent_lat,
    m.longitude                  AS mergent_lon,
    m.street_address             AS mergent_street,
    m.city                       AS mergent_city,
    m.zip                        AS mergent_zip
FROM f7_employers_deduped f
LEFT JOIN corporate_identifier_crosswalk cw
       ON cw.f7_employer_id = f.employer_id
LEFT JOIN mergent_employers m
       ON m.duns = cw.mergent_duns
WHERE f.state = 'NY'
  AND f.is_historical = FALSE
  AND f.latitude IS NOT NULL
  AND f.longitude IS NOT NULL
  AND COALESCE(m.employees_all_sites, f.latest_unit_size) > 1000
"""


def fetch_candidates(conn) -> pd.DataFrame:
    df = pd.read_sql(SELECTION_SQL, conn)
    # Collapse duplicates from multiple union relations: one row per employer,
    # first parent_union seen.
    df = df.sort_values("parent_union").drop_duplicates("f7_employer_id", keep="first")
    return df.reset_index(drop=True)


def derive_workplace_location(row: pd.Series) -> Tuple[float, float, str]:
    """
    Returns (lat, lon, source_tag). Prefer mergent address when single-site,
    else fall back to f7 address.
    """
    has_mergent = pd.notna(row.get("mergent_duns"))
    ratio = None
    if has_mergent and row.get("employees_site") and row.get("employees_all_sites"):
        try:
            ratio = float(row["employees_site"]) / float(row["employees_all_sites"])
        except (ZeroDivisionError, ValueError):
            ratio = None

    if has_mergent and ratio is not None and ratio >= 0.70 \
            and pd.notna(row.get("mergent_lat")) and pd.notna(row.get("mergent_lon")):
        return float(row["mergent_lat"]), float(row["mergent_lon"]), "mergent_single_site"

    if pd.notna(row.get("mergent_lat")) and pd.notna(row.get("mergent_lon")) \
            and ratio is not None and ratio < 0.70:
        # Mergent-matched but site is much smaller than total — HQ rollup risk.
        return float(row["f7_lat"]), float(row["f7_lon"]), "f7_multi_site_caveat"

    # No mergent match — trust the F7 address as the single site (per user).
    return float(row["f7_lat"]), float(row["f7_lon"]), "f7_no_mergent"


def map_to_cns(naics6: Optional[str], naics_detailed: Optional[str], naics_raw: Optional[str]) -> Optional[str]:
    for val in (naics6, naics_detailed, naics_raw):
        if val and isinstance(val, str) and len(val) >= 2:
            return NAICS_TO_CNS.get(val[:2])
    return None


def spatial_join_tract(lat: float, lon: float, tracts: gpd.GeoDataFrame) -> Optional[pd.Series]:
    pt = gpd.GeoDataFrame({"geometry": [Point(lon, lat)]}, crs="EPSG:4326")
    joined = gpd.sjoin(pt, tracts[["GEOID", "county_fips", "NAMELSAD", "geometry"]],
                       how="left", predicate="within")
    if joined.empty or pd.isna(joined.iloc[0]["GEOID"]):
        return None
    return joined.iloc[0]


def pick_diverse(bucket: pd.DataFrame, n: int) -> pd.DataFrame:
    """
    Pick n rows maximizing CNS diversity. Greedy: each pick maximizes a new CNS
    sector relative to the already-picked set, ties broken by employee count.
    """
    if bucket.empty:
        return bucket.iloc[0:0]
    picked: List[int] = []
    remaining = bucket.copy()
    while len(picked) < n and not remaining.empty:
        used_cns = set(bucket.loc[picked]["cns_sector"].dropna().tolist()) if picked else set()
        remaining["_cns_new"] = remaining["cns_sector"].apply(
            lambda c: 0 if (pd.isna(c) or c in used_cns) else 1)
        remaining = remaining.sort_values(
            ["_cns_new", "estimated_employees"], ascending=[False, False]
        )
        idx = remaining.index[0]
        picked.append(idx)
        remaining = remaining.drop(idx)
    return bucket.loc[picked].copy()


def run_selection(conn, shapes: Shapes, out_dir: Path) -> pd.DataFrame:
    cands = fetch_candidates(conn)
    print(f"  Raw candidates (>1000 employees, NY F7, geocoded): {len(cands):,}")

    # Derive workplace location
    locs = cands.apply(derive_workplace_location, axis=1)
    cands["workplace_lat"] = [x[0] for x in locs]
    cands["workplace_lon"] = [x[1] for x in locs]
    cands["workplace_source"] = [x[2] for x in locs]

    # Employee estimate + single-site flag
    cands["estimated_employees"] = cands["employees_all_sites"].fillna(cands["latest_unit_size"])
    cands["site_share"] = (
        cands["employees_site"].astype("Float64")
        / cands["employees_all_sites"].replace({0: np.nan}).astype("Float64")
    )
    cands["is_single_site"] = cands.apply(
        lambda r: (
            (pd.isna(r["mergent_duns"])) or
            (pd.notna(r["site_share"]) and r["site_share"] >= 0.70)
        ),
        axis=1,
    )

    # NAICS -> CNS
    cands["cns_sector"] = cands.apply(
        lambda r: map_to_cns(r["mergent_naics6"], r["f7_naics_detailed"], r["f7_naics"]),
        axis=1,
    )

    # Exclude employers where workplace_source flagged HQ rollup risk
    before = len(cands)
    cands = cands[cands["workplace_source"] != "f7_multi_site_caveat"].copy()
    print(f"  Dropped {before - len(cands)} HQ-rollup candidates (Mergent site<70% of all)")

    # Spatial-join to workplace tract + county
    tracts_small = shapes.tracts[["GEOID", "county_fips", "NAMELSAD", "geometry"]]
    pts = gpd.GeoDataFrame(
        cands.assign(geometry=[Point(lon, lat) for lon, lat in zip(cands["workplace_lon"], cands["workplace_lat"])]),
        geometry="geometry", crs="EPSG:4326",
    )
    joined = gpd.sjoin(pts, tracts_small, how="left", predicate="within")
    # sjoin can duplicate rows if a point lies on a tract boundary; keep first.
    joined = joined[~joined.index.duplicated(keep="first")]
    cands["workplace_tract"] = joined["GEOID"].values
    cands["workplace_county_fips"] = joined["county_fips"].values
    cands["workplace_tract_name"] = joined["NAMELSAD"].values

    before = len(cands)
    cands = cands.dropna(subset=["workplace_tract"])
    print(f"  Dropped {before - len(cands)} candidates with no NY tract match (outside state)")

    # Require a CNS mapping
    before = len(cands)
    cands = cands.dropna(subset=["cns_sector"]).copy()
    print(f"  Dropped {before - len(cands)} candidates with no NAICS->CNS mapping")

    # Split NYC / non-NYC
    nyc = cands[cands["workplace_county_fips"].isin(NYC_COUNTY_FIPS)].copy()
    other = cands[~cands["workplace_county_fips"].isin(NYC_COUNTY_FIPS)].copy()
    print(f"  Pool: {len(nyc)} NYC candidates, {len(other)} non-NYC candidates")

    picks_nyc = pick_diverse(nyc, n=5)
    picks_nyc["bucket"] = "NYC"
    picks_other = pick_diverse(other, n=5)
    picks_other["bucket"] = "Non-NYC"
    picks = pd.concat([picks_nyc, picks_other], ignore_index=True)
    picks["rank"] = range(1, len(picks) + 1)

    # Final columns
    keep = [
        "rank", "bucket", "f7_employer_id", "employer_name", "parent_union",
        "estimated_employees", "is_single_site", "workplace_source",
        "mergent_naics6", "f7_naics_detailed", "f7_naics", "cns_sector",
        "workplace_tract", "workplace_county_fips", "workplace_tract_name",
        "workplace_lat", "workplace_lon",
        "f7_street", "f7_city", "f7_zip",
        "mergent_street", "mergent_city", "mergent_zip",
        "employees_site", "employees_all_sites", "latest_unit_size", "site_share",
    ]
    picks_out = picks[keep].copy()

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "data" / "employer_picks.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    picks_out.to_csv(csv_path, index=False)

    print()
    print("=== PICKED EMPLOYERS ===")
    for _, r in picks_out.iterrows():
        county_name = NYC_COUNTY_NAMES.get(r["workplace_county_fips"], "")
        tag = "SINGLE" if r["is_single_site"] else "MULTI "
        print(f"  #{r['rank']:2d} [{r['bucket']:<7s}] [{tag}] {r['employer_name'][:55]:<55s}  "
              f"~{int(r['estimated_employees']):>7,} emp   "
              f"{r['cns_sector']}   "
              f"{county_name or r['workplace_county_fips']}   "
              f"{r['parent_union'][:30] if r['parent_union'] else ''}")
    print()
    print(f"Wrote {csv_path}")
    return picks_out


# ---------------------------------------------------------------------------
# Commute-shed computation
# ---------------------------------------------------------------------------

def compute_cns_share(conn, workplace_tract: str, cns: str) -> Tuple[float, int, int]:
    """
    Returns (cns_share, cns_jobs, total_jobs) for a workplace tract.
    """
    cns_col = cns.lower()
    sql = f"""
        SELECT SUM(c000) AS c000_total,
               SUM({cns_col}) AS cns_total
          FROM lodes_wac_2022
         WHERE SUBSTRING(w_geocode, 1, 11) = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, [workplace_tract])
        c000_total, cns_total = cur.fetchone()
    c000_total = int(c000_total or 0)
    cns_total = int(cns_total or 0)
    share = cns_total / c000_total if c000_total > 0 else 0.0
    return share, cns_total, c000_total


def fetch_home_tract_flows(conn, workplace_tract: str) -> pd.DataFrame:
    sql = """
        SELECT SUBSTRING(h_geocode, 1, 11) AS home_tract,
               SUM(s000)                   AS total_jobs,
               SUM(CASE WHEN od_type='aux' THEN s000 ELSE 0 END) AS aux_jobs
          FROM lodes_od_2022
         WHERE SUBSTRING(w_geocode, 1, 11) = %s
         GROUP BY 1
    """
    df = pd.read_sql(sql, conn, params=[workplace_tract])
    return df


def label_tract(centroid: Point, ntas: gpd.GeoDataFrame, cousubs: gpd.GeoDataFrame,
                tract_name: str, county_name: str) -> str:
    pt = gpd.GeoDataFrame({"geometry": [centroid]}, crs="EPSG:4326")
    nta_hit = gpd.sjoin(pt, ntas, how="left", predicate="within")
    if not nta_hit.empty and pd.notna(nta_hit.iloc[0].get("ntaname")):
        return str(nta_hit.iloc[0]["ntaname"])
    sub_hit = gpd.sjoin(pt, cousubs, how="left", predicate="within")
    if not sub_hit.empty and pd.notna(sub_hit.iloc[0].get("NAMELSAD")):
        return str(sub_hit.iloc[0]["NAMELSAD"])
    return f"{tract_name}, {county_name} County"


def fetch_acs_map(conn) -> pd.DataFrame:
    sql = """
        SELECT tract_fips,
               county_fips,
               median_household_income
          FROM acs_tract_demographics
         WHERE state_fips = '36'
    """
    return pd.read_sql(sql, conn)


def county_name_for_fips(fips: str, counties: gpd.GeoDataFrame) -> str:
    if fips in NYC_COUNTY_NAMES:
        return NYC_COUNTY_NAMES[fips]
    row = counties[counties["GEOID"] == fips]
    if row.empty:
        return fips
    return str(row.iloc[0]["NAME"])


def compute_commute_shed(conn, emp: pd.Series, shapes: Shapes, acs_df: pd.DataFrame
                          ) -> Tuple[pd.DataFrame, Dict]:
    workplace_tract = emp["workplace_tract"]
    cns = emp["cns_sector"]

    cns_share, cns_jobs, c000_total = compute_cns_share(conn, workplace_tract, cns)
    flows = fetch_home_tract_flows(conn, workplace_tract)

    if flows.empty or cns_share <= 0 or c000_total == 0:
        return pd.DataFrame(), {"cns_share": cns_share, "cns_jobs": cns_jobs,
                                "wac_c000": c000_total, "od_s000": 0, "aux_share": 0.0}

    flows["est_workers"] = flows["total_jobs"] * cns_share
    total_est = flows["est_workers"].sum()
    flows["share_of_workforce"] = flows["est_workers"] / total_est if total_est > 0 else 0.0

    # Attach geography
    geo = shapes.tracts[["GEOID", "county_fips", "NAMELSAD", "geometry"]].rename(
        columns={"GEOID": "home_tract"})
    flows = flows.merge(geo, on="home_tract", how="left")

    # Some home tracts may be outside NY (aux flows from NJ/CT/PA). Drop them
    # from the NY choropleth but keep their share accounted for in totals.
    flows_ny = flows.dropna(subset=["geometry"]).copy()
    flows_ny = gpd.GeoDataFrame(flows_ny, geometry="geometry", crs="EPSG:4326")

    # Join ACS median HHI
    flows_ny = flows_ny.merge(
        acs_df.rename(columns={"tract_fips": "home_tract"})[["home_tract", "median_household_income"]],
        on="home_tract", how="left",
    )

    # Label tract names
    centroids = flows_ny.geometry.centroid
    county_names = flows_ny["county_fips"].apply(lambda f: county_name_for_fips(f, shapes.counties))
    flows_ny["label"] = [
        label_tract(c, shapes.ntas, shapes.cousubs, n, cn)
        for c, n, cn in zip(centroids, flows_ny["NAMELSAD"], county_names)
    ]
    flows_ny["county_name"] = county_names.values

    metrics = {
        "cns_share": cns_share,
        "cns_jobs": cns_jobs,
        "wac_c000": c000_total,
        "od_s000": int(flows["total_jobs"].sum()),
        "aux_share": float(flows["aux_jobs"].sum() / flows["total_jobs"].sum())
            if flows["total_jobs"].sum() > 0 else 0.0,
        "ny_share_of_flows": float(flows_ny["total_jobs"].sum() / flows["total_jobs"].sum())
            if flows["total_jobs"].sum() > 0 else 0.0,
        "total_est_workers": float(total_est),
    }
    return flows_ny, metrics


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", (s or "").lower())
    return s.strip("_")[:40]


def render_static(emp: pd.Series, flows: gpd.GeoDataFrame, shapes: Shapes,
                  out_path: Path, buffer_deg: float = 0.9):
    if flows.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 10))

    # Choropleth via quantile breaks on share_of_workforce (cap at tracts with share > 0)
    choro = flows[flows["share_of_workforce"] > 0].copy()
    vmin = choro["share_of_workforce"].min()
    vmax = choro["share_of_workforce"].quantile(0.98) if len(choro) > 20 else choro["share_of_workforce"].max()

    # Base: NY state counties outline, faint
    shapes.counties.boundary.plot(ax=ax, edgecolor="#888888", linewidth=0.4)

    # Tracts, only those with data, colored; faint outline on all
    shapes.tracts.boundary.plot(ax=ax, edgecolor="#e5e5e5", linewidth=0.2)
    choro.plot(ax=ax, column="share_of_workforce", cmap="YlOrRd",
               vmin=vmin, vmax=vmax,
               legend=True, legend_kwds={
                   "label": "Share of apportioned workforce",
                   "shrink": 0.6, "format": "%.1f%%",
                   "orientation": "horizontal", "pad": 0.02,
               })

    # Workplace pin
    ax.plot(emp["workplace_lon"], emp["workplace_lat"], "*", color="#0033aa",
            markersize=18, markeredgecolor="white", markeredgewidth=1.2,
            zorder=10)

    # Zoom: center on workplace + buffer
    cx, cy = emp["workplace_lon"], emp["workplace_lat"]
    ax.set_xlim(cx - buffer_deg, cx + buffer_deg)
    ax.set_ylim(cy - buffer_deg * 0.85, cy + buffer_deg * 0.85)
    ax.set_axis_off()

    title = f"{emp['employer_name']}"
    subtitle = (
        f"{emp['parent_union'] or 'Unknown union'} · "
        f"~{int(emp['estimated_employees']):,} employees · "
        f"NAICS {emp.get('mergent_naics6') or emp.get('f7_naics_detailed') or emp.get('f7_naics')} "
        f"({emp['cns_sector']})"
    )
    ax.set_title(title, fontsize=14, weight="bold", loc="left")
    ax.text(0.01, 0.965, subtitle, transform=ax.transAxes, fontsize=10, color="#444")
    ax.text(0.01, 0.02,
            "Color = share of apportioned workforce living in each tract.\n"
            "Apportionment: LODES OD 2022 × workplace-tract CNS share from WAC.",
            transform=ax.transAxes, fontsize=8, color="#666", va="bottom")

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def render_interactive(emp: pd.Series, flows: gpd.GeoDataFrame, out_path: Path):
    if flows.empty:
        return
    m = folium.Map(location=[emp["workplace_lat"], emp["workplace_lon"]],
                   zoom_start=10, tiles="OpenStreetMap")

    choro = flows[flows["share_of_workforce"] > 0].copy()
    if choro.empty:
        return
    choro["share_pct"] = choro["share_of_workforce"] * 100
    vmax = float(choro["share_pct"].quantile(0.98))
    vmin = float(choro["share_pct"].min())

    cmap = cm.linear.YlOrRd_09.scale(vmin, vmax if vmax > vmin else vmin + 0.01)
    cmap.caption = "Share of apportioned workforce (%)"

    def style_fn(feat):
        share = feat["properties"]["share_pct"]
        return {
            "fillColor": cmap(min(share, vmax)) if share > 0 else "#f0f0f0",
            "color": "#555",
            "weight": 0.3,
            "fillOpacity": 0.75,
        }

    folium.GeoJson(
        choro[["home_tract", "label", "county_name", "est_workers",
               "share_pct", "median_household_income", "geometry"]].to_json(),
        style_function=style_fn,
        tooltip=folium.GeoJsonTooltip(
            fields=["label", "county_name", "home_tract", "est_workers",
                    "share_pct", "median_household_income"],
            aliases=["Neighborhood/Town", "County", "Tract FIPS",
                     "Est. workers", "Share %", "Median HHI"],
            localize=True,
            labels=True,
            sticky=True,
        ),
    ).add_to(m)
    cmap.add_to(m)

    popup_html = (
        f"<b>{emp['employer_name']}</b><br>"
        f"{emp['parent_union'] or ''}<br>"
        f"~{int(emp['estimated_employees']):,} employees<br>"
        f"NAICS {emp.get('mergent_naics6') or emp.get('f7_naics_detailed') or emp.get('f7_naics')}"
        f" ({emp['cns_sector']})"
    )
    folium.Marker(
        location=[emp["workplace_lat"], emp["workplace_lon"]],
        popup=folium.Popup(popup_html, max_width=300),
        icon=folium.Icon(color="blue", icon="briefcase", prefix="fa"),
    ).add_to(m)

    title_html = (
        f'<h3 style="position:fixed;top:10px;left:50px;z-index:9999;'
        f'background:white;padding:6px 10px;border:1px solid #ccc;'
        f'font-family:sans-serif;">{emp["employer_name"]} — commute shed</h3>'
    )
    m.get_root().html.add_child(folium.Element(title_html))

    m.save(str(out_path))


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify(emp: pd.Series, flows: gpd.GeoDataFrame, metrics: Dict) -> List[Dict]:
    checks = []
    name = emp["employer_name"]
    eid = emp["f7_employer_id"]

    # 1. OD vs WAC self-consistency for the workplace tract.
    if metrics["wac_c000"] > 0:
        diff = abs(metrics["od_s000"] - metrics["wac_c000"]) / metrics["wac_c000"]
        status = "PASS" if diff <= 0.02 else "WARN" if diff <= 0.10 else "FAIL"
        checks.append({"check": "od_wac_self_consistency", "status": status,
                       "detail": f"OD={metrics['od_s000']:,} WAC={metrics['wac_c000']:,} diff={diff:.2%}"})
    else:
        checks.append({"check": "od_wac_self_consistency", "status": "FAIL",
                       "detail": "WAC c000=0 for workplace tract"})

    # 2. Apportioned workforce vs reported employer size.
    est_emp = float(emp.get("estimated_employees") or 0)
    total = metrics.get("total_est_workers") or 0.0
    if est_emp > 0:
        ratio = total / est_emp
        if 0.5 <= ratio <= 5.0:
            status = "PASS"
        elif 0.1 <= ratio <= 10.0:
            status = "WARN"
        else:
            status = "FAIL"
        checks.append({"check": "workforce_bound", "status": status,
                       "detail": f"apportioned={total:,.0f} vs employer={est_emp:,.0f} ratio={ratio:.2f}x"})
    else:
        checks.append({"check": "workforce_bound", "status": "SKIP",
                       "detail": "no employer size"})

    # 3. Top-10 home tract county contains workplace county.
    top = flows.sort_values("est_workers", ascending=False).head(10) if not flows.empty else flows
    if not top.empty:
        counties = set(top["county_fips"].astype(str))
        has_wp = emp["workplace_county_fips"] in counties
        status = "PASS" if has_wp else "WARN"
        checks.append({"check": "geographic_plausibility", "status": status,
                       "detail": f"workplace_county={emp['workplace_county_fips']} in top10_counties={sorted(counties)[:5]}..."})
    else:
        checks.append({"check": "geographic_plausibility", "status": "FAIL",
                       "detail": "no flows"})

    # 4. NYC aux contribution sanity.
    if emp["workplace_county_fips"] in NYC_COUNTY_FIPS:
        aux = metrics.get("aux_share", 0.0)
        status = "PASS" if 0.10 <= aux <= 0.50 else "WARN"
        checks.append({"check": "nyc_aux_share", "status": status,
                       "detail": f"aux_share={aux:.1%} (expect 10-40%)"})

    return [{"employer": name, "id": eid, **c} for c in checks]


def write_verification_log(records: List[Dict], out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("employer | id | check | status | detail\n")
        f.write("-" * 100 + "\n")
        for r in records:
            f.write(f"{r['employer']} | {r['id']} | {r['check']} | {r['status']} | {r['detail']}\n")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def do_run(conn, picks: pd.DataFrame, shapes: Shapes, out_dir: Path):
    acs = fetch_acs_map(conn)
    (out_dir / "maps_static").mkdir(parents=True, exist_ok=True)
    (out_dir / "maps_interactive").mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)

    all_checks: List[Dict] = []
    summary_rows: List[Dict] = []

    for _, emp in picks.iterrows():
        rank = int(emp["rank"])
        slug = _slug(emp["employer_name"])
        eid = emp["f7_employer_id"]
        print(f"\n#{rank} {emp['employer_name']} ({eid})")

        flows, metrics = compute_commute_shed(conn, emp, shapes, acs)
        if flows.empty:
            print("  (no flows; skipping map)")
            all_checks.extend(verify(emp, flows, metrics))
            continue

        # Top-10 CSV
        top10 = (flows.sort_values("est_workers", ascending=False)
                      .head(10)
                      [["home_tract", "label", "county_name", "est_workers",
                        "share_of_workforce", "median_household_income"]]
                      .copy())
        top10["share_pct"] = (top10["share_of_workforce"] * 100).round(2)
        top10["est_workers"] = top10["est_workers"].round(1)
        top10.to_csv(out_dir / "data" / f"top_home_tracts_{eid}.csv", index=False)
        print(f"  top tract: {top10.iloc[0]['label']} ({top10.iloc[0]['share_pct']:.1f}% share)")

        # Maps
        static_path = out_dir / "maps_static" / f"{rank:02d}_{eid}_{slug}.png"
        html_path = out_dir / "maps_interactive" / f"{rank:02d}_{eid}_{slug}.html"
        render_static(emp, flows, shapes, static_path)
        render_interactive(emp, flows, html_path)
        print(f"  wrote {static_path.name} + {html_path.name}")

        # Verification
        all_checks.extend(verify(emp, flows, metrics))

        summary_rows.append({
            "rank": rank, "f7_employer_id": eid,
            "employer_name": emp["employer_name"],
            "parent_union": emp["parent_union"],
            "cns_sector": emp["cns_sector"],
            "estimated_employees": emp["estimated_employees"],
            "workplace_tract": emp["workplace_tract"],
            "workplace_county": emp["workplace_county_fips"],
            "workplace_lat": emp["workplace_lat"],
            "workplace_lon": emp["workplace_lon"],
            "cns_share": round(metrics["cns_share"], 4),
            "cns_jobs_workplace_tract": metrics["cns_jobs"],
            "total_est_workers": round(metrics["total_est_workers"], 1),
            "aux_share": round(metrics["aux_share"], 4),
            "ny_share_of_flows": round(metrics["ny_share_of_flows"], 4),
            "top_home_label": top10.iloc[0]["label"],
            "top_home_share_pct": round(float(top10.iloc[0]["share_pct"]), 2),
            "static_map": str(static_path.relative_to(out_dir)),
            "interactive_map": str(html_path.relative_to(out_dir)),
        })

    write_verification_log(all_checks, out_dir / "data" / "verification_log.txt")
    pd.DataFrame(summary_rows).to_csv(out_dir / "data" / "summary.csv", index=False)
    print(f"\nVerification log: {out_dir / 'data' / 'verification_log.txt'}")
    print(f"Summary CSV:      {out_dir / 'data' / 'summary.csv'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--select-only", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTDIR))
    args = ap.parse_args()

    if not (args.select_only or args.run or args.all):
        ap.error("pass one of --select-only / --run / --all")

    out_dir = Path(args.output_dir)
    shapes = load_shapes()
    conn = get_connection()
    try:
        if args.select_only or args.all:
            picks = run_selection(conn, shapes, out_dir)
            if args.select_only:
                return
        else:
            picks_path = out_dir / "data" / "employer_picks.csv"
            if not picks_path.exists():
                raise SystemExit(f"Picks file missing: {picks_path}. Run --select-only first.")
            picks = pd.read_csv(picks_path)

        do_run(conn, picks, shapes, out_dir)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
