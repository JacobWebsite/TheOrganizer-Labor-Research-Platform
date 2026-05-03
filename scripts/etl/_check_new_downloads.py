"""One-off script to check new download files for dupes and load unique ones."""
import pandas as pd
import shutil
import tempfile
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection

all_files = [
    r"C:\Users\jakew\Downloads\25_advancesearch156882071869c9b0d7d98be.csv",
    r"C:\Users\jakew\Downloads\25_advancesearch156629686569c9b0c1d2f56.csv",
    r"C:\Users\jakew\Downloads\23_advancesearch63803644569c9b05e71fb5.csv",
    r"C:\Users\jakew\Downloads\21_advancesearch140398112069c9b02f876cc (1).csv",
    r"C:\Users\jakew\Downloads\21_advancesearch140398112069c9b02f876cc.csv",
    r"C:\Users\jakew\Downloads\22_advancesearch20542141369c9b04559cfc (1).csv",
    r"C:\Users\jakew\Downloads\22_advancesearch20542141369c9b04559cfc.csv",
    r"C:\Users\jakew\Downloads\20_advancesearch71844421169c9b01b85eb3 (1).csv",
    r"C:\Users\jakew\Downloads\20_advancesearch71844421169c9b01b85eb3.csv",
    r"C:\Users\jakew\Downloads\18_advancesearch121699492069c9aeddd1656 (2).csv",
    r"C:\Users\jakew\Downloads\18_advancesearch94792824869c9af987122b.csv",
    r"C:\Users\jakew\Downloads\15_advancesearch23877788069c9ae8d166c7 (1).csv",
    r"C:\Users\jakew\Downloads\16_advancesearch202285007569c9aec19acfd (1).csv",
    r"C:\Users\jakew\Downloads\18_advancesearch121699492069c9aeddd1656 (1).csv",
    r"C:\Users\jakew\Downloads\18_advancesearch121699492069c9aeddd1656.csv",
    r"C:\Users\jakew\Downloads\16_advancesearch95617604869c9af88aa70a.csv",
    r"C:\Users\jakew\Downloads\15_advancesearch23877788069c9ae8d166c7.csv",
    r"C:\Users\jakew\Downloads\17_advancesearch74544158069c9aea6eb32d.csv",
    r"C:\Users\jakew\Downloads\16_advancesearch202285007569c9aec19acfd.csv",
    r"C:\Users\jakew\Downloads\13_advancesearch109141958669c9ae071d38f.csv",
    r"C:\Users\jakew\Downloads\14_advancesearch99795798569c9ae1fe9759.csv",
    r"C:\Users\jakew\Downloads\11_advancesearch107240066469c9add15271f.csv",
    r"C:\Users\jakew\Downloads\9_advancesearch169979002969c9adb150166.csv",
    r"C:\Users\jakew\Downloads\12_advancesearch189546948769c9adef3e759.csv",
    r"C:\Users\jakew\Downloads\8_advancesearch120184872969c9ada02b1fd.csv",
    r"C:\Users\jakew\Downloads\8_advancesearch113552294069c9ad2c09e2f.csv",
    r"C:\Users\jakew\Downloads\7_advancesearch106847313269c9ad1d729c2.csv",
    r"C:\Users\jakew\Downloads\5_advancesearch130364420369c9acfc3a7a0.csv",
    r"C:\Users\jakew\Downloads\6_advancesearch147839132469c9ad0dbc8b5.csv",
    r"C:\Users\jakew\Downloads\4_advancesearch81537404669c9aceb31f8e.csv",
    r"C:\Users\jakew\Downloads\3_advancesearch3971630869c9ab68f24ab.csv",
    r"C:\Users\jakew\Downloads\2_advancesearch131963306969c9aaf45ec5c.csv",
    r"C:\Users\jakew\Downloads\1_advancesearch58381120369c9aa854b713.csv",
    r"C:\Users\jakew\Downloads\3_advancesearch203644884069c9a83ba696b (1).csv",
    r"C:\Users\jakew\Downloads\2_advancesearch195861196569c9a69d0dc51 (2).csv",
    r"C:\Users\jakew\Downloads\3_advancesearch203644884069c9a83ba696b.csv",
    r"C:\Users\jakew\Downloads\3_advancesearch21652672769c9a7858c5c1 (1).csv",
    r"C:\Users\jakew\Downloads\2_advancesearch195861196569c9a69d0dc51 (1).csv",
    r"C:\Users\jakew\Downloads\2_advancesearch167086858069c9a77b6e593.csv",
    r"C:\Users\jakew\Downloads\3_advancesearch21652672769c9a7858c5c1.csv",
    r"C:\Users\jakew\Downloads\2_advancesearch195861196569c9a69d0dc51.csv",
    r"C:\Users\jakew\Downloads\3_advancesearch106743529669c9a6a830517.csv",
    r"C:\Users\jakew\Downloads\1_advancesearch102053185069c9a668126e0.csv",
    r"C:\Users\jakew\Downloads\12_advancesearch121498596769c95ca1ebadc.csv",
    r"C:\Users\jakew\Downloads\10_advancesearch67171021369c95c8df32fe (1).csv",
    r"C:\Users\jakew\Downloads\9_advancesearch190362521469c95c88944a9 (1).csv",
    r"C:\Users\jakew\Downloads\8_advancesearch16686899169c95c7f9b585 (1).csv",
    r"C:\Users\jakew\Downloads\8_advancesearch16686899169c95c7f9b585.csv",
    r"C:\Users\jakew\Downloads\9_advancesearch190362521469c95c88944a9.csv",
    r"C:\Users\jakew\Downloads\10_advancesearch67171021369c95c8df32fe.csv",
    r"C:\Users\jakew\Downloads\3_advancesearch66058837969c95bfc7af5d (1).csv",
    r"C:\Users\jakew\Downloads\4_advancesearch33897119169c95c6c1fab9.csv",
    r"C:\Users\jakew\Downloads\1_advancesearch187419098369c95bef1d2ac (1).csv",
    r"C:\Users\jakew\Downloads\3_advancesearch66058837969c95bfc7af5d.csv",
    r"C:\Users\jakew\Downloads\1_advancesearch187419098369c95bef1d2ac.csv",
    r"C:\Users\jakew\Downloads\6_advancesearch181870997969c9580da5b7d.csv",
    r"C:\Users\jakew\Downloads\7_advancesearch180142132469c957db4454c.csv",
    r"C:\Users\jakew\Downloads\5_advancesearch151977973469c957ada88df.csv",
    r"C:\Users\jakew\Downloads\4_advancesearch54438369469c957996883f.csv",
    r"C:\Users\jakew\Downloads\3_advancesearch124955300969c9572b8657c.csv",
    r"C:\Users\jakew\Downloads\15_advancesearch55639921069c956f434875.csv",
    r"C:\Users\jakew\Downloads\16_advancesearch78711609069c956f91210a.csv",
    r"C:\Users\jakew\Downloads\2_advancesearch54338238369c95668b8baf.csv",
    r"C:\Users\jakew\Downloads\3_advancesearch37620639669c9567175089.csv",
    r"C:\Users\jakew\Downloads\4_advancesearch196459683869c956757d489.csv",
]

# Filter to existing CSV files
existing = [f for f in all_files if os.path.exists(f) and f.endswith(".csv")]
skipped = [f for f in all_files if not os.path.exists(f) or not f.endswith(".csv")]
print("Files found: %d, missing/skipped: %d" % (len(existing), len(skipped)))

# Fingerprint
file_duns = {}
for fpath in existing:
    fname = os.path.basename(fpath)
    tmp = tempfile.mktemp(suffix=".xlsx")
    shutil.copy2(fpath, tmp)
    try:
        df = pd.read_excel(tmp, sheet_name=0, engine="openpyxl")
    except Exception as e:
        print("  SKIP %s: %s" % (fname, e))
        continue
    finally:
        os.unlink(tmp)
    duns_set = frozenset(
        str(row.get("D-U-N-S@ Number", "")).replace("-", "").strip()
        for _, row in df.iterrows() if pd.notna(row.get("D-U-N-S@ Number"))
    )
    file_duns[fname] = (fpath, duns_set)

# Dedup
groups = []
assigned = set()
fnames = list(file_duns.keys())
for i in range(len(fnames)):
    if fnames[i] in assigned:
        continue
    group = [fnames[i]]
    assigned.add(fnames[i])
    for j in range(i + 1, len(fnames)):
        if fnames[j] in assigned:
            continue
        if file_duns[fnames[i]][1] == file_duns[fnames[j]][1]:
            group.append(fnames[j])
            assigned.add(fnames[j])
    groups.append(group)

print("\n%d files -> %d unique groups, %d duplicates" % (len(file_duns), len(groups), len(file_duns) - len(groups)))

# Check which are already loaded
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT file_path FROM mergent_load_progress")
loaded_fnames = set(os.path.basename(r[0]) for r in cur.fetchall() if r[0])

new_to_load = []
already_loaded = []
for g in groups:
    fname = g[0]
    fpath = file_duns[fname][0]
    if fname in loaded_fnames:
        already_loaded.append((fname, len(g)))
    else:
        new_to_load.append(fpath)

# Check new DUNS against DB
new_duns = set()
for fpath in new_to_load:
    fname = os.path.basename(fpath)
    new_duns.update(file_duns[fname][1])

if new_duns:
    duns_list = list(new_duns)
    # Chunk the query to avoid too-large IN clause
    already_in_db = 0
    for chunk_start in range(0, len(duns_list), 5000):
        chunk = duns_list[chunk_start:chunk_start + 5000]
        cur.execute("SELECT COUNT(*) FROM mergent_employers WHERE duns IN (%s)" % ",".join(["%s"] * len(chunk)), chunk)
        already_in_db += cur.fetchone()[0]
else:
    already_in_db = 0

print("\nAlready loaded: %d groups" % len(already_loaded))
print("New to load: %d unique files" % len(new_to_load))
print("New unique DUNS across new files: %d" % len(new_duns))
print("Already in DB: %d" % already_in_db)
print("Genuinely new companies: %d" % (len(new_duns) - already_in_db))

print("\n--- FILES TO LOAD ---")
for f in new_to_load:
    print(f)

conn.close()
