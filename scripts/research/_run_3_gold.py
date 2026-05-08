"""Run 3 gold standard research dossiers to test Tier 1+2 changes."""
import sys
import time
sys.path.insert(0, ".")

from scripts.research.agent import run_research
from db_config import get_connection

companies = [
    ("Burgerville", "OR", "722513", "private"),
    ("King David Center for Nursing and Rehabilitation", "NY", "623110", "private"),
    ("Warrior Met Coal", "AL", "212112", "public"),
]

for name, state, naics, ctype in companies:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO research_runs (company_name, company_state, industry_naics, company_type, status, created_at)"
        " VALUES (%s, %s, %s, %s, 'pending', NOW()) RETURNING id",
        (name, state, naics, ctype),
    )
    run_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    print(f"Starting {name} (run #{run_id})...", flush=True)
    t0 = time.time()
    result = run_research(run_id)
    dur = time.time() - t0
    print(f"  -> {result['status']} | facts={result.get('facts_saved', 0)} | {dur:.0f}s")

    # Check cost tracking + quality
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT total_input_tokens, total_output_tokens, total_cost_cents, overall_quality_score"
        " FROM research_runs WHERE id = %s",
        (run_id,),
    )
    r = cur.fetchone()
    cost_dollars = float(r[2] or 0) / 100
    print(f"  -> tokens: in={r[0]} out={r[1]} cost=${cost_dollars:.4f} quality={r[3]}")
    cur.close()
    conn.close()

print("Done.")
