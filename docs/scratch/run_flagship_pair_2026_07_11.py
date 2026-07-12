"""Run the two new flagship dossiers: Yale University + Montefiore Medical Center.

Flagship-5 v2 (approved 2026-07-11): Yale (master 92892), Montefiore (master 155254),
Pacific Lutheran, Graceland Fruit, Bronson Battle Creek (last three already gold).
Run AFTER the 61-batch finishes (serial Gemini usage, keeps circuit breakers clean).

Usage:  cd <project root> && export PYTHONPATH=. && py docs/scratch/run_flagship_pair_2026_07_11.py
"""
import sys

sys.path.insert(0, ".")

from db_config import get_connection
from scripts.research.batch_research import (
    submit_research_run,
    run_single,
    grade_and_enhance,
)

FLAGSHIPS = [
    ("92892", "Yale University"),
    ("155254", "Montefiore Medical Center"),
]


def main():
    conn = get_connection()
    cur = conn.cursor()

    for master_id, label in FLAGSHIPS:
        cur.execute(
            "SELECT display_name, state, naics FROM mv_target_scorecard WHERE master_id::text = %s",
            (master_id,),
        )
        row = cur.fetchone()
        if not row:
            print(f"SKIP {label}: master {master_id} not in mv_target_scorecard")
            continue
        name, state, naics = row
        print(f"[flagship] {name} ({state}) master={master_id} ...")
        run_id = submit_research_run(master_id, name, state, naics)
        result = run_single(run_id)
        status = result.get("status", "unknown")
        print(f"  -> {status} (run #{run_id})")
        if status == "completed":
            grade_and_enhance(run_id)
            # Flagship dossiers join the gold-standard set.
            cur2 = conn.cursor()
            cur2.execute(
                "UPDATE research_runs SET is_gold_standard = TRUE, gold_standard_at = NOW() WHERE id = %s",
                (run_id,),
            )
            conn.commit()
            print(f"  -> marked gold standard (run #{run_id})")

    conn.close()


if __name__ == "__main__":
    main()
