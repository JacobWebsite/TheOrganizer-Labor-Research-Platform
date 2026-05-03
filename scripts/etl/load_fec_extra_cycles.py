"""
Append extra FEC cycles (indiv22, indiv26) to the existing
`fec_individual_contributions` table without dropping the schema.

The main `load_fec.py` is single-cycle (2023-24) and DROPs+CREATEs the
table on every run. This wrapper imports its helpers and runs only the
indiv ingestion against additional cycle files, relying on the existing
`ON CONFLICT (sub_id) DO NOTHING` to make multi-cycle loads idempotent.

Usage (after `load_fec.py` has loaded the indiv24 cycle):
    py scripts/etl/load_fec_extra_cycles.py

Reads:
    files/fec/indiv22.zip   (2021-22 cycle)
    files/fec/indiv26.zip   (2025-26 cycle, partial)

Skips any cycle file that doesn't exist.
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from db_config import get_connection
import scripts.etl.load_fec as fec


def load_indiv_from(zip_name: str, cur, conn) -> int:
    """Load the indiv file at files/fec/<zip_name> into fec_individual_contributions.

    Mirrors fec._load_indiv but takes the zip name explicitly so we can run
    against indiv22.zip and indiv26.zip in sequence.
    """
    from psycopg2.extras import execute_values
    zip_path = fec.FEC_DIR / zip_name
    if not zip_path.exists():
        print(f"SKIP: {zip_path} not found")
        return 0

    print(f"Loading {zip_name} into fec_individual_contributions...")
    t0 = time.time()
    BATCH = 5000
    sql = """
        INSERT INTO fec_individual_contributions (
            cmte_id, amndt_ind, rpt_tp, transaction_pgi, image_num,
            transaction_tp, entity_tp, name, city, state, zip_code,
            employer, occupation, transaction_dt, transaction_amt,
            other_id, tran_id, file_num, memo_cd, memo_text, sub_id,
            employer_norm
        ) VALUES %s
        ON CONFLICT (sub_id) DO NOTHING
    """
    batch, total, skipped = [], 0, 0
    seen = set()
    for r in fec._stream_rows(zip_path):
        if len(r) < 21:
            skipped += 1
            continue
        sub_id = fec._norm_int(r[20])
        if sub_id is None or sub_id in seen:
            skipped += 1
            continue
        seen.add(sub_id)
        emp_norm = fec._norm_employer(r[11])
        batch.append((
            fec._truncate(r[0], 9), fec._truncate(r[1], 1), fec._truncate(r[2], 3),
            fec._truncate(r[3], 5), fec._truncate(r[4], 20), fec._truncate(r[5], 3),
            fec._truncate(r[6], 3), fec._truncate(r[7], 200), fec._truncate(r[8], 30),
            fec._norm_state(r[9]), fec._truncate(r[10], 10), fec._truncate(r[11], 38),
            fec._truncate(r[12], 38), fec._norm_date(r[13]), fec._norm_decimal(r[14]),
            fec._truncate(r[15], 9), fec._truncate(r[16], 40), fec._norm_int(r[17]),
            fec._truncate(r[18], 1), fec._truncate(r[19], 100), sub_id, emp_norm,
        ))
        if len(batch) >= BATCH:
            execute_values(cur, sql, batch, page_size=BATCH)
            total += len(batch)
            batch = []
            if total % 200_000 == 0:
                print(f"  Loaded {total:,} rows ({time.time()-t0:.0f}s elapsed)")
    if batch:
        execute_values(cur, sql, batch, page_size=BATCH)
        total += len(batch)
    conn.commit()
    print(f"  Loaded {total:,} rows from {zip_name} ({skipped:,} skipped) in {time.time()-t0:.0f}s")
    return total


def main():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM fec_individual_contributions")
    before = cur.fetchone()[0]
    print(f"BEFORE: {before:,} rows in fec_individual_contributions")

    total22 = load_indiv_from("indiv22.zip", cur, conn)
    total26 = load_indiv_from("indiv26.zip", cur, conn)

    cur.execute("SELECT COUNT(*) FROM fec_individual_contributions")
    after = cur.fetchone()[0]
    print(f"\nAFTER: {after:,} rows in fec_individual_contributions")
    print(f"Net new: {after - before:,} rows ({total22:,} from cycle 22 + {total26:,} from cycle 26 minus dedup)")

    cur.execute("""
        SELECT MIN(transaction_dt), MAX(transaction_dt)
        FROM fec_individual_contributions
        WHERE transaction_dt IS NOT NULL
    """)
    dmin, dmax = cur.fetchone()
    print(f"Date range: {dmin} -> {dmax}")

    conn.close()


if __name__ == "__main__":
    main()
