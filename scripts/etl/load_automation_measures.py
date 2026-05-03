"""
Load 4 automation measures + crosswalks + China trade data into PostgreSQL.

Files expected in C:\\Users\\jakew\\Downloads\\automation_measures\\:
- AIOE-main/AIOE_DataAppendix.xlsx (Felten AIOE - Appendix A, B, C)
- AIOE-main/Image Generation AIOE and AIIE.xlsx
- AIOE-main/Language Modeling AIOE and AIIE.xlsx
- occ1990dd_task_alm.zip (Autor-Dorn task scores)
- occ1990dd_task_offshore.zip
- china9114.zip (ADH China shock)
- occ2000_occ1990dd.zip
- occ2010_occ1990dd.zip
- frey_osborne_probabilities.csv (extracted from FO paper)
"""
from __future__ import annotations

import argparse
import os
import sys
import math
import zipfile
import tempfile
from io import StringIO

import psycopg2
import pandas as pd
import numpy as np


DL = r"C:\Users\jakew\Downloads\automation_measures"


def get_conn():
    return psycopg2.connect(
        dbname="olms_multiyear", user="postgres",
        password="Juniordog33!", host="localhost",
    )


SCHEMA_SQL = """
DROP TABLE IF EXISTS automation_felten_aioe CASCADE;
CREATE TABLE automation_felten_aioe (
    soc_code VARCHAR(10) PRIMARY KEY,
    occupation_title TEXT,
    aioe NUMERIC
);

DROP TABLE IF EXISTS automation_felten_aiie CASCADE;
CREATE TABLE automation_felten_aiie (
    id SERIAL PRIMARY KEY,
    naics_code VARCHAR(10),
    industry_title TEXT,
    aiie NUMERIC
);

DROP TABLE IF EXISTS automation_felten_aige CASCADE;
CREATE TABLE automation_felten_aige (
    fips_code VARCHAR(10) PRIMARY KEY,
    geographic_area TEXT,
    aige NUMERIC,
    geography_level VARCHAR(20)
);

DROP TABLE IF EXISTS automation_felten_generative CASCADE;
CREATE TABLE automation_felten_generative (
    id SERIAL PRIMARY KEY,
    soc_code VARCHAR(10),
    model_type VARCHAR(30),
    occupation_title TEXT,
    aioe NUMERIC
);

DROP TABLE IF EXISTS automation_autor_dorn_tasks CASCADE;
CREATE TABLE automation_autor_dorn_tasks (
    occ1990dd INTEGER PRIMARY KEY,
    task_abstract NUMERIC,
    task_routine NUMERIC,
    task_manual NUMERIC,
    task_offshorability NUMERIC,
    rti NUMERIC
);

DROP TABLE IF EXISTS automation_frey_osborne CASCADE;
CREATE TABLE automation_frey_osborne (
    soc_code VARCHAR(10) PRIMARY KEY,
    occupation_title TEXT,
    probability NUMERIC,
    label NUMERIC,
    rank INTEGER
);

DROP TABLE IF EXISTS xwalk_occ2000_1990dd CASCADE;
CREATE TABLE xwalk_occ2000_1990dd (
    occ2000 INTEGER PRIMARY KEY,
    occ1990dd INTEGER
);

DROP TABLE IF EXISTS xwalk_occ2010_1990dd CASCADE;
CREATE TABLE xwalk_occ2010_1990dd (
    occ2010 VARCHAR(10) PRIMARY KEY,
    occ1990dd INTEGER
);

DROP TABLE IF EXISTS adh_china_trade CASCADE;
CREATE TABLE adh_china_trade (
    sic87dd INTEGER,
    year INTEGER,
    importer VARCHAR(10),
    exporter VARCHAR(10),
    imports NUMERIC,
    PRIMARY KEY (sic87dd, year, importer, exporter)
);
CREATE INDEX idx_adh_sic_year ON adh_china_trade (sic87dd, year);
"""


def step_schema(conn):
    print("[SCHEMA] Creating tables...")
    cur = conn.cursor()
    cur.execute(SCHEMA_SQL)
    conn.commit()
    print("  Tables created.")


def extract_zip_if_needed(zname, target_dir_name=None):
    """Extract zip into a subdirectory; return path to extracted dir."""
    zpath = os.path.join(DL, zname)
    if not os.path.exists(zpath):
        return None
    subdir = os.path.join(DL, target_dir_name or zname.replace(".zip", ""))
    if not os.path.exists(subdir):
        os.makedirs(subdir, exist_ok=True)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(subdir)
    return subdir


def load_felten_aioe(conn):
    print("[FELTEN AIOE]")
    xl = os.path.join(DL, "AIOE-main", "AIOE_DataAppendix.xlsx")
    if not os.path.exists(xl):
        print(f"  MISSING: {xl}")
        return

    # Appendix A: SOC-level AIOE
    df = pd.read_excel(xl, sheet_name="Appendix A", skiprows=0)
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={"SOC Code": "soc_code",
                            "Occupation Title": "occupation_title",
                            "AIOE": "aioe"})
    df = df[["soc_code", "occupation_title", "aioe"]].dropna(subset=["soc_code"])
    df = df.drop_duplicates(subset="soc_code", keep="first")
    print(f"  Appendix A: {len(df)} rows")

    cur = conn.cursor()
    cur.execute("TRUNCATE automation_felten_aioe")
    buf = StringIO()
    for _, r in df.iterrows():
        title = (str(r["occupation_title"]) if pd.notna(r["occupation_title"]) else "").replace("\t", " ").replace("\n", " ")
        aioe = "" if pd.isna(r["aioe"]) else str(r["aioe"])
        buf.write(f"{r['soc_code']}\t{title}\t{aioe}\n")
    buf.seek(0)
    cur.copy_expert("COPY automation_felten_aioe FROM STDIN WITH (FORMAT text, NULL '')", buf)
    conn.commit()
    print(f"  Loaded {len(df)} rows to automation_felten_aioe")

    # Appendix B: AIIE by NAICS 4-digit
    dfb = pd.read_excel(xl, sheet_name="Appendix B")
    dfb.columns = [c.strip() for c in dfb.columns]
    dfb = dfb.rename(columns={"NAICS": "naics_code",
                              "Industry Title": "industry_title",
                              "AIIE": "aiie"})
    dfb = dfb[["naics_code", "industry_title", "aiie"]].dropna(subset=["naics_code"])
    print(f"  Appendix B: {len(dfb)} rows")

    cur.execute("TRUNCATE automation_felten_aiie RESTART IDENTITY")
    buf = StringIO()
    for _, r in dfb.iterrows():
        code = str(int(r["naics_code"])) if isinstance(r["naics_code"], (int, float)) and not pd.isna(r["naics_code"]) else str(r["naics_code"])
        title = (str(r["industry_title"]) if pd.notna(r["industry_title"]) else "").replace("\t", " ").replace("\n", " ")
        aiie = "" if pd.isna(r["aiie"]) else str(r["aiie"])
        buf.write(f"{code}\t{title}\t{aiie}\n")
    buf.seek(0)
    cur.copy_expert("COPY automation_felten_aiie (naics_code, industry_title, aiie) FROM STDIN WITH (FORMAT text, NULL '')", buf)
    conn.commit()
    print(f"  Loaded {len(dfb)} rows to automation_felten_aiie")

    # Appendix C: AIGE by FIPS
    dfc = pd.read_excel(xl, sheet_name="Appendix C")
    dfc.columns = [c.strip() for c in dfc.columns]
    dfc = dfc.rename(columns={"FIPS Code": "fips_code",
                              "Geographic Area": "geographic_area",
                              "AIGE": "aige"})
    dfc = dfc[["fips_code", "geographic_area", "aige"]].dropna(subset=["fips_code"])

    def geo_level(fc):
        s = str(fc).strip()
        if len(s) == 2:
            return "state"
        if s.endswith("000") and len(s) == 5:
            return "state"
        if len(s) == 5:
            return "county"
        return "other"

    dfc["geography_level"] = dfc["fips_code"].apply(geo_level)
    dfc = dfc.drop_duplicates(subset="fips_code", keep="first")
    print(f"  Appendix C: {len(dfc)} rows")

    cur.execute("TRUNCATE automation_felten_aige")
    buf = StringIO()
    for _, r in dfc.iterrows():
        fc = str(r["fips_code"]).strip()
        ga = (str(r["geographic_area"]) if pd.notna(r["geographic_area"]) else "").replace("\t", " ").replace("\n", " ")
        aige = "" if pd.isna(r["aige"]) else str(r["aige"])
        buf.write(f"{fc}\t{ga}\t{aige}\t{r['geography_level']}\n")
    buf.seek(0)
    cur.copy_expert("COPY automation_felten_aige FROM STDIN WITH (FORMAT text, NULL '')", buf)
    conn.commit()
    print(f"  Loaded {len(dfc)} rows to automation_felten_aige")


def load_felten_generative(conn):
    print("[FELTEN GENERATIVE]")
    cur = conn.cursor()
    cur.execute("TRUNCATE automation_felten_generative RESTART IDENTITY")

    for fname, mtype in [
        ("Image Generation AIOE and AIIE.xlsx", "image_generation"),
        ("Language Modeling AIOE and AIIE.xlsx", "language_modeling"),
    ]:
        xl = os.path.join(DL, "AIOE-main", fname)
        if not os.path.exists(xl):
            print(f"  MISSING: {fname}")
            continue
        try:
            # First sheet should be AIOE occ-level
            sheets = pd.ExcelFile(xl).sheet_names
            # Find sheet with SOC/AIOE
            for sname in sheets:
                df = pd.read_excel(xl, sheet_name=sname)
                df.columns = [c.strip() for c in df.columns]
                col_map = {}
                for c in df.columns:
                    lc = c.lower()
                    if "soc" in lc: col_map[c] = "soc_code"
                    elif "title" in lc or "occupation" in lc: col_map[c] = "occupation_title"
                    elif "aioe" in lc: col_map[c] = "aioe"
                if "soc_code" in col_map.values() and "aioe" in col_map.values():
                    df = df.rename(columns=col_map)
                    df = df[["soc_code", "occupation_title", "aioe"]].dropna(subset=["soc_code", "aioe"])
                    df = df.drop_duplicates(subset="soc_code", keep="first")
                    buf = StringIO()
                    for _, r in df.iterrows():
                        title = (str(r["occupation_title"]) if pd.notna(r["occupation_title"]) else "").replace("\t", " ").replace("\n", " ")
                        buf.write(f"{r['soc_code']}\t{mtype}\t{title}\t{r['aioe']}\n")
                    buf.seek(0)
                    cur.copy_expert("COPY automation_felten_generative (soc_code, model_type, occupation_title, aioe) FROM STDIN WITH (FORMAT text, NULL '')", buf)
                    print(f"  {mtype}: {len(df)} rows from sheet '{sname}'")
                    break
        except Exception as e:
            print(f"  ERROR {fname}: {e}")
    conn.commit()


def load_autor_dorn(conn):
    print("[AUTOR-DORN TASKS]")
    # Extract and load task ALM data
    alm_dir = extract_zip_if_needed("occ1990dd_task_alm.zip")
    if not alm_dir:
        print("  MISSING task ALM zip")
        return
    alm_files = [f for f in os.listdir(alm_dir) if f.endswith(".dta")]
    if not alm_files:
        print("  NO .dta file in ALM zip")
        return
    alm = pd.read_stata(os.path.join(alm_dir, alm_files[0]))
    print(f"  ALM rows: {len(alm)}, cols: {list(alm.columns)}")

    # Extract and load offshorability
    off_dir = extract_zip_if_needed("occ1990dd_task_offshore.zip")
    off = None
    if off_dir:
        off_files = [f for f in os.listdir(off_dir) if f.endswith(".dta")]
        if off_files:
            off = pd.read_stata(os.path.join(off_dir, off_files[0]))
            print(f"  Offshore rows: {len(off)}, cols: {list(off.columns)}")

    # Merge
    merged = alm.copy()
    if off is not None and "occ1990dd" in off.columns:
        merged = merged.merge(off, on="occ1990dd", how="outer")

    # Compute RTI = ln(routine) - ln(abstract) - ln(manual)
    # Handle zeros/negatives with epsilon
    EPS = 1e-3
    def safe_ln(x):
        if pd.isna(x) or x <= 0:
            return np.nan
        return math.log(max(x, EPS))
    merged["rti"] = (
        merged["task_routine"].apply(safe_ln)
        - merged["task_abstract"].apply(safe_ln)
        - merged["task_manual"].apply(safe_ln)
    )

    cur = conn.cursor()
    cur.execute("TRUNCATE automation_autor_dorn_tasks")
    buf = StringIO()
    for _, r in merged.iterrows():
        if pd.isna(r.get("occ1990dd")):
            continue
        occ = int(r["occ1990dd"])
        ta = "" if pd.isna(r.get("task_abstract")) else str(r["task_abstract"])
        tr = "" if pd.isna(r.get("task_routine")) else str(r["task_routine"])
        tm = "" if pd.isna(r.get("task_manual")) else str(r["task_manual"])
        to = "" if pd.isna(r.get("task_offshorability")) else str(r["task_offshorability"])
        rti = "" if pd.isna(r.get("rti")) else str(r["rti"])
        buf.write(f"{occ}\t{ta}\t{tr}\t{tm}\t{to}\t{rti}\n")
    buf.seek(0)
    cur.copy_expert("COPY automation_autor_dorn_tasks FROM STDIN WITH (FORMAT text, NULL '')", buf)
    conn.commit()
    print(f"  Loaded {len(merged)} rows to automation_autor_dorn_tasks")


def load_frey_osborne(conn):
    print("[FREY-OSBORNE]")
    csv_path = os.path.join(DL, "frey_osborne_probabilities.csv")
    if not os.path.exists(csv_path):
        print(f"  MISSING: {csv_path}")
        return
    df = pd.read_csv(csv_path)
    df = df.drop_duplicates(subset="soc_code", keep="first")
    print(f"  Rows: {len(df)}")

    cur = conn.cursor()
    cur.execute("TRUNCATE automation_frey_osborne")
    buf = StringIO()
    for _, r in df.iterrows():
        label = "" if pd.isna(r["label"]) else str(int(r["label"]))
        occ = (str(r["occupation"]) if pd.notna(r["occupation"]) else "").replace("\t", " ").replace("\n", " ")
        buf.write(f"{r['soc_code']}\t{occ}\t{r['probability']}\t{label}\t{int(r['rank'])}\n")
    buf.seek(0)
    cur.copy_expert("COPY automation_frey_osborne FROM STDIN WITH (FORMAT text, NULL '')", buf)
    conn.commit()
    print(f"  Loaded {len(df)} rows to automation_frey_osborne")


def load_crosswalks(conn):
    print("[CROSSWALKS]")
    cur = conn.cursor()

    for zname, table, src_col, dtype in [
        ("occ2000_occ1990dd.zip", "xwalk_occ2000_1990dd", "occ", "int"),
        ("occ2010_occ1990dd.zip", "xwalk_occ2010_1990dd", "occ", "str"),
    ]:
        d = extract_zip_if_needed(zname)
        if not d:
            print(f"  MISSING: {zname}")
            continue
        dtas = [f for f in os.listdir(d) if f.endswith(".dta")]
        if not dtas:
            continue
        df = pd.read_stata(os.path.join(d, dtas[0]))
        print(f"  {zname}: {len(df)} rows, cols: {list(df.columns)}")

        cur.execute(f"TRUNCATE {table}")
        buf = StringIO()
        for _, r in df.iterrows():
            src = r.get(src_col)
            if pd.isna(src) or pd.isna(r.get("occ1990dd")):
                continue
            if dtype == "int":
                src_v = int(src)
            else:
                src_v = str(src).strip()
            dst_v = int(r["occ1990dd"])
            buf.write(f"{src_v}\t{dst_v}\n")
        buf.seek(0)
        cur.copy_expert(f"COPY {table} FROM STDIN WITH (FORMAT text, NULL '')", buf)
        conn.commit()
        print(f"  Loaded to {table}")


def load_china_trade(conn):
    print("[ADH CHINA TRADE]")
    d = extract_zip_if_needed("china9114.zip")
    if not d:
        print("  MISSING china9114.zip")
        return
    dtas = [f for f in os.listdir(d) if f.endswith(".dta")]
    if not dtas:
        print("  NO .dta in china9114")
        return
    df = pd.read_stata(os.path.join(d, dtas[0]))
    print(f"  Rows: {len(df):,}, cols: {list(df.columns)}")

    cur = conn.cursor()
    cur.execute("TRUNCATE adh_china_trade")
    buf = StringIO()
    n = 0
    for _, r in df.iterrows():
        try:
            sic = int(r["sic87dd"])
            yr = int(r["year"])
            imp = str(r["importer"]).strip()
            exp = str(r["exporter"]).strip()
            imports = "" if pd.isna(r.get("imports")) else str(r["imports"])
            buf.write(f"{sic}\t{yr}\t{imp}\t{exp}\t{imports}\n")
            n += 1
        except Exception:
            continue
    buf.seek(0)
    cur.copy_expert("COPY adh_china_trade FROM STDIN WITH (FORMAT text, NULL '')", buf)
    conn.commit()
    print(f"  Loaded {n:,} rows")


def step_verify(conn):
    print("\n[VERIFY]")
    cur = conn.cursor()
    for t in [
        "automation_felten_aioe",
        "automation_felten_aiie",
        "automation_felten_aige",
        "automation_felten_generative",
        "automation_autor_dorn_tasks",
        "automation_frey_osborne",
        "xwalk_occ2000_1990dd",
        "xwalk_occ2010_1990dd",
        "adh_china_trade",
    ]:
        cur.execute(f"SELECT count(*) FROM {t}")
        n = cur.fetchone()[0]
        print(f"  {t}: {n:,}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", default="all", choices=["schema", "load", "verify", "all"])
    args = parser.parse_args()

    conn = get_conn()
    try:
        if args.step in ("schema", "all"):
            step_schema(conn)
        if args.step in ("load", "all"):
            load_felten_aioe(conn)
            load_felten_generative(conn)
            load_autor_dorn(conn)
            load_frey_osborne(conn)
            load_crosswalks(conn)
            load_china_trade(conn)
        if args.step in ("verify", "all"):
            step_verify(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
