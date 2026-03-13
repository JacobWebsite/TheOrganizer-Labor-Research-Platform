"""Build SLD transit score table from EPA Smart Location Database V3.

Extracts transit accessibility and walkability scores from the .gdb file
inside SmartLocationDatabaseV3.zip, writes to PostgreSQL sld_transit_scores
table + backup sld_transit_scores.json.

Key columns: GEOID10 (Census block group), D4a (aggregate transit freq),
D4c (transit freq by type), D5tr (jobs accessible by transit),
NatWalkInd (walkability index).

Source: SmartLocationDatabaseV3.zip (.gdb format, requires geopandas/fiona)

Usage:
    py scripts/analysis/demographics_comparison/build_sld_transit_table.py
"""
import sys
import os
import json
import zipfile
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection

SCRIPT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
SLD_ZIP = os.path.join(PROJECT_ROOT, 'SmartLocationDatabaseV3.zip')

# Transit score thresholds (based on D4a aggregate transit frequency)
TIER_THRESHOLDS = {
    'none': 0,       # D4a = 0
    'minimal': 10,   # D4a < 10
    'moderate': 50,  # D4a < 50
    'high': 50,      # D4a >= 50
}


def compute_transit_score(d4a, d4c, d5tr, natwalkind):
    """Compute composite transit score (0-100) from SLD variables.

    D4a: Aggregate transit frequency (stops per sq mi)
    D4c: Transit frequency by type
    D5tr: Jobs accessible by transit (45-min trip)
    NatWalkInd: National walkability index (1-20)
    """
    # Normalize each component to 0-100
    # D4a: log scale, typical range 0-200+
    import math
    d4a_score = min(100, 50 * math.log1p(d4a or 0) / math.log1p(200))

    # D5tr: typical range 0-500000+
    d5tr_score = min(100, 50 * math.log1p(d5tr or 0) / math.log1p(500000))

    # NatWalkInd: range 1-20, linear scale
    walk_score = min(100, ((natwalkind or 1) - 1) / 19 * 100)

    # Weighted average: transit frequency 40%, job access 30%, walkability 30%
    score = 0.40 * d4a_score + 0.30 * d5tr_score + 0.30 * walk_score
    return round(score, 2)


def compute_transit_tier(d4a):
    """Classify transit tier based on aggregate frequency."""
    if d4a is None or d4a == 0:
        return 'none'
    elif d4a < 10:
        return 'minimal'
    elif d4a < 50:
        return 'moderate'
    else:
        return 'high'


def main():
    print('BUILD SLD TRANSIT SCORES')
    print('=' * 60)

    if not os.path.exists(SLD_ZIP):
        print('ERROR: SLD zip not found: %s' % SLD_ZIP)
        sys.exit(1)

    # Try to import geopandas
    try:
        import geopandas as gpd
        print('geopandas available')
    except ImportError:
        print('geopandas not installed. Attempting pip install...')
        import subprocess
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', 'geopandas'],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print('pip install geopandas failed:')
            print(result.stderr[:500])
            print('')
            print('Falling back to CSV download approach...')
            print('Please install geopandas manually: pip install geopandas')
            sys.exit(1)
        import geopandas as gpd
        print('geopandas installed successfully')

    # Extract .gdb from zip to temp directory
    print('Extracting .gdb from zip...')
    tmpdir = tempfile.mkdtemp(prefix='sld_')
    gdb_path = None

    try:
        with zipfile.ZipFile(SLD_ZIP, 'r') as zf:
            # Find the .gdb directory inside the zip
            gdb_entries = [n for n in zf.namelist() if '.gdb/' in n or n.endswith('.gdb')]
            if not gdb_entries:
                print('ERROR: No .gdb found in zip')
                sys.exit(1)

            # Extract all .gdb entries
            gdb_root = gdb_entries[0].split('.gdb/')[0] + '.gdb'
            print('Found: %s (%d files)' % (gdb_root, len(gdb_entries)))
            zf.extractall(tmpdir)
            gdb_path = os.path.join(tmpdir, gdb_root)

        if not os.path.exists(gdb_path):
            # Try to find it
            for root, dirs, files in os.walk(tmpdir):
                for d in dirs:
                    if d.endswith('.gdb'):
                        gdb_path = os.path.join(root, d)
                        break

        print('Reading .gdb: %s' % gdb_path)

        # Read only needed columns
        columns_needed = ['GEOID10', 'D4A', 'D4C', 'D5TR', 'NATWALKIND']
        # Try reading with column filter; geopandas may need to read all
        try:
            # First list layers
            import fiona
            layers = fiona.listlayers(gdb_path)
            print('Layers: %s' % layers)
            layer_name = layers[0] if layers else None
        except Exception:
            layer_name = None

        print('Loading SLD data (this may take a minute)...')
        gdf = gpd.read_file(gdb_path, layer=layer_name)
        print('Loaded %d block groups' % len(gdf))
        print('Columns: %s' % list(gdf.columns[:20]))

        # Normalize column names to uppercase for matching
        col_map = {c.upper(): c for c in gdf.columns}

        def get_col(name):
            return col_map.get(name.upper(), name)

        geoid_col = get_col('GEOID10')
        d4a_col = get_col('D4A')
        d4c_col = get_col('D4C')
        d5tr_col = get_col('D5TR')
        walk_col = get_col('NATWALKIND')

        # Process each block group
        results = {}
        processed = 0
        missing_geoid = 0

        for _, row in gdf.iterrows():
            geoid = str(row.get(geoid_col, '')).strip()
            if not geoid or len(geoid) < 12:
                missing_geoid += 1
                continue

            def safe_float(val, default=0):
                try:
                    v = float(val)
                    return default if v < -1 else v  # -99999 = missing sentinel
                except (TypeError, ValueError):
                    return default

            d4a = safe_float(row.get(d4a_col, 0), 0)
            d4c = safe_float(row.get(d4c_col, 0), 0)
            d5tr = safe_float(row.get(d5tr_col, 0), 0)
            natwalkind = safe_float(row.get(walk_col, 1), 1)

            transit_score = compute_transit_score(d4a, d4c, d5tr, natwalkind)
            transit_tier = compute_transit_tier(d4a)

            results[geoid] = {
                'd4a': round(d4a, 2),
                'd5tr': round(d5tr, 1),
                'natwalkind': round(natwalkind, 2),
                'transit_score': transit_score,
                'transit_tier': transit_tier,
            }
            processed += 1

        print('Processed: %d block groups' % processed)
        print('Missing GEOID: %d' % missing_geoid)

    finally:
        # Clean up temp directory
        if tmpdir and os.path.exists(tmpdir):
            shutil.rmtree(tmpdir, ignore_errors=True)
            print('Cleaned up temp directory')

    if not results:
        print('ERROR: No results computed.')
        sys.exit(1)

    # Summary stats
    scores = [v['transit_score'] for v in results.values()]
    scores.sort()
    tiers = {}
    for v in results.values():
        t = v['transit_tier']
        tiers[t] = tiers.get(t, 0) + 1
    print('')
    print('Transit score distribution:')
    print('  Min: %.1f' % scores[0])
    print('  P25: %.1f' % scores[len(scores) // 4])
    print('  Median: %.1f' % scores[len(scores) // 2])
    print('  P75: %.1f' % scores[3 * len(scores) // 4])
    print('  Max: %.1f' % scores[-1])
    print('Transit tiers: %s' % tiers)

    # Save JSON backup
    json_path = os.path.join(SCRIPT_DIR, 'sld_transit_scores.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f)
    print('')
    print('Saved JSON: %s (%d entries, %.1f MB)' % (
        json_path, len(results), os.path.getsize(json_path) / 1e6))

    # Write to PostgreSQL
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sld_transit_scores (
            geoid10 VARCHAR(12) PRIMARY KEY,
            d4a NUMERIC(10,2),
            d5tr NUMERIC(12,1),
            natwalkind NUMERIC(5,2),
            transit_score NUMERIC(5,2),
            transit_tier VARCHAR(10)
        )
    """)
    cur.execute("TRUNCATE sld_transit_scores")

    from psycopg2.extras import execute_batch
    batch = []
    for geoid, data in results.items():
        batch.append((
            geoid, data['d4a'], data['d5tr'], data['natwalkind'],
            data['transit_score'], data['transit_tier'],
        ))

    # Insert in chunks to avoid memory issues
    chunk_size = 5000
    total_inserted = 0
    for i in range(0, len(batch), chunk_size):
        chunk = batch[i:i + chunk_size]
        execute_batch(cur, """
            INSERT INTO sld_transit_scores
                (geoid10, d4a, d5tr, natwalkind, transit_score, transit_tier)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, chunk)
        total_inserted += len(chunk)
        if total_inserted % 50000 == 0:
            print('  Inserted %d/%d...' % (total_inserted, len(batch)))

    conn.commit()
    print('Loaded %d rows into sld_transit_scores table' % len(batch))

    conn.close()
    print('Done.')


if __name__ == '__main__':
    main()
