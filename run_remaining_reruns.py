"""
B4 Remaining Re-runs — Sequential Runner
Runs all remaining source re-runs, then refreshes materialized views.

Usage:  py run_remaining_reruns.py
        py run_remaining_reruns.py --skip-990    (skip 990, start with WHD)
        py run_remaining_reruns.py --skip-to-sam  (skip to SAM only)
        py run_remaining_reruns.py --refresh-only (just refresh MVs)
"""
import subprocess, sys, time, json, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def run(cmd, label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  Command: {cmd}")
    print(f"  Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n", flush=True)
    t0 = time.time()
    result = subprocess.run(cmd, shell=True)
    elapsed = time.time() - t0
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
    print(f"\n  >> {label}: {status} in {mins}m {secs}s\n", flush=True)
    return result.returncode == 0

def check_990_batch(n):
    """Check if 990 batch n is already done via checkpoint."""
    cp = "checkpoints/990_rerun.json"
    if not os.path.exists(cp):
        return False
    with open(cp) as f:
        data = json.load(f)
    batch_info = data.get("batches", {}).get(str(n), {})
    return batch_info.get("completed_at") is not None

args = set(sys.argv[1:])

steps = []

if "--refresh-only" not in args:
    # 990 batches 2-5
    if "--skip-990" not in args and "--skip-to-sam" not in args:
        for batch in range(2, 6):
            if check_990_batch(batch):
                print(f"990 batch {batch}/5 already done, skipping.")
            else:
                steps.append((
                    f"py scripts/matching/run_deterministic.py 990 --rematch-all --batch {batch}/5",
                    f"990 batch {batch}/5 (~117K records)"
                ))

    # WHD solo
    if "--skip-to-sam" not in args:
        steps.append((
            "py scripts/matching/run_deterministic.py whd --rematch-all",
            "WHD full re-run (~363K records, solo)"
        ))

    # SAM batched (826K records, 5 batches)
    steps.append((
        "py scripts/matching/run_deterministic.py sam --rematch-all --batch 1/5",
        "SAM batch 1/5 (~165K records)"
    ))
    steps.append((
        "py scripts/matching/run_deterministic.py sam --rematch-all --batch 2/5",
        "SAM batch 2/5 (~165K records)"
    ))
    steps.append((
        "py scripts/matching/run_deterministic.py sam --rematch-all --batch 3/5",
        "SAM batch 3/5 (~165K records)"
    ))
    steps.append((
        "py scripts/matching/run_deterministic.py sam --rematch-all --batch 4/5",
        "SAM batch 4/5 (~165K records)"
    ))
    steps.append((
        "py scripts/matching/run_deterministic.py sam --rematch-all --batch 5/5",
        "SAM batch 5/5 (~165K records)"
    ))

# Rebuild legacy match tables from UML (handles any legacy write failures)
steps.append((
    "py scripts/maintenance/rebuild_legacy_tables.py",
    "Rebuild legacy match tables from UML"
))

# MV refreshes (always run at the end)
steps.append((
    "py scripts/scoring/create_scorecard_mv.py --refresh",
    "Refresh mv_organizing_scorecard"
))
steps.append((
    "py scripts/scoring/build_employer_data_sources.py --refresh",
    "Refresh mv_employer_data_sources"
))
steps.append((
    "py scripts/scoring/build_unified_scorecard.py --refresh",
    "Refresh mv_unified_scorecard"
))

print(f"\n{'#'*60}")
print(f"  B4 REMAINING RE-RUNS + MV REFRESH")
print(f"  {len(steps)} steps to run sequentially")
print(f"  Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'#'*60}\n")

t_start = time.time()
results = []

for i, (cmd, label) in enumerate(steps, 1):
    print(f"[{i}/{len(steps)}]", flush=True)
    ok = run(cmd, label)
    results.append((label, ok))
    if not ok:
        print(f"\n!! Step failed: {label}")
        print(f"!! Stopping. Re-run with appropriate --skip flag to resume.\n")
        break

elapsed = time.time() - t_start
hrs = int(elapsed // 3600)
mins = int((elapsed % 3600) // 60)

print(f"\n{'#'*60}")
print(f"  SUMMARY — {hrs}h {mins}m total")
print(f"{'#'*60}")
for label, ok in results:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
remaining = len(steps) - len(results)
if remaining:
    print(f"  ...  {remaining} steps not reached")
print()
