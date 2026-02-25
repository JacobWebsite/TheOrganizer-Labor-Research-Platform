"""
Phase 1B Investigation Sprint Runner.

Runs all 8 new investigation scripts + verification pass,
then generates a consolidated PHASE_1B_SUMMARY.md.

Usage:
    py scripts/analysis/run_phase_1b.py --all
    py scripts/analysis/run_phase_1b.py --tier 1
    py scripts/analysis/run_phase_1b.py --only I11 I17
    py scripts/analysis/run_phase_1b.py --verify-only
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
INVESTIGATIONS_DIR = os.path.join(PROJECT_ROOT, "docs", "investigations")

# All Phase 1B investigations
INVESTIGATIONS = [
    # Tier 1 - Quick
    {
        "id": "I11",
        "tier": 1,
        "topic": "Geocoding gap by score tier",
        "script": "investigate_geocoding_gap.py",
        "output": "I11_geocoding_gap_by_tier.md",
    },
    {
        "id": "I17",
        "tier": 1,
        "topic": "Score distribution after Phase 1",
        "script": "investigate_score_distribution.py",
        "output": "I17_score_distribution_phase1.md",
    },
    {
        "id": "I18",
        "tier": 1,
        "topic": "Active unions (filed LM in last 3 years)",
        "script": "investigate_active_unions.py",
        "output": "I18_active_unions.md",
    },
    {
        "id": "I20",
        "tier": 1,
        "topic": "Corporate hierarchy Factor 1 coverage",
        "script": "investigate_corporate_hierarchy.py",
        "output": "I20_corporate_hierarchy_coverage.md",
    },
    # Tier 2 - Medium
    {
        "id": "I19",
        "tier": 2,
        "topic": "Mel-Ro Construction OSHA spot check",
        "script": "investigate_mel_ro.py",
        "output": "I19_mel_ro_spot_check.md",
    },
    {
        "id": "I15",
        "tier": 2,
        "topic": "Missing source ID linkages root cause",
        "script": "investigate_missing_linkages.py",
        "output": "I15_missing_source_id_linkages.md",
    },
    {
        "id": "I14",
        "tier": 2,
        "topic": "Legacy poisoned matches (non-SAM)",
        "script": "investigate_legacy_matches.py",
        "output": "I14_legacy_poisoned_matches.md",
    },
    # Tier 3 - Complex
    {
        "id": "I12",
        "tier": 3,
        "topic": "Geographic enforcement bias",
        "script": "investigate_enforcement_bias.py",
        "output": "I12_geographic_enforcement_bias.md",
    },
]

VERIFICATION = {
    "id": "VERIFY",
    "tier": 0,
    "topic": "Verification pass on completed investigations",
    "script": "verify_completed_investigations.py",
    "output": "VERIFICATION_PASS.md",
}


def run_script(entry, project_root):
    """Run a single investigation script. Returns (success, duration_s, error_msg)."""
    script_path = os.path.join(SCRIPT_DIR, entry["script"])
    output_path = os.path.join(INVESTIGATIONS_DIR, entry["output"])

    if not os.path.exists(script_path):
        return False, 0, f"Script not found: {script_path}"

    cmd = [sys.executable, script_path, "--output", output_path]
    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
        duration = time.time() - start
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "Unknown error").strip()
            # Truncate long errors
            if len(err) > 500:
                err = err[:500] + "..."
            return False, duration, err
        return True, duration, None
    except subprocess.TimeoutExpired:
        return False, 300, "Timed out after 300s"
    except Exception as e:
        return False, time.time() - start, str(e)


def read_report_summary(output_file):
    """Read the first few meaningful lines from a report for the consolidated summary."""
    path = os.path.join(INVESTIGATIONS_DIR, output_file)
    if not os.path.exists(path):
        return "Report file not found."
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return "Could not read report."

    # Find the Summary section and extract first paragraph
    in_summary = False
    summary_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Summary") or stripped.startswith("## Findings"):
            in_summary = True
            continue
        if in_summary:
            if stripped.startswith("## "):
                break
            if stripped:
                summary_lines.append(stripped)
            if len(summary_lines) >= 5:
                break
    if summary_lines:
        return " ".join(summary_lines)
    return "No summary section found in report."


def generate_consolidated_summary(results, verify_result):
    """Generate PHASE_1B_SUMMARY.md from all results."""
    lines = []
    lines.append("# Phase 1B Investigation Sprint - Consolidated Summary")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # Overall status
    succeeded = sum(1 for r in results if r["success"])
    failed = sum(1 for r in results if not r["success"])
    total_time = sum(r["duration"] for r in results)
    lines.append("## Overall Status")
    lines.append("")
    lines.append(f"- **Investigations run:** {len(results)}")
    lines.append(f"- **Succeeded:** {succeeded}")
    lines.append(f"- **Failed:** {failed}")
    lines.append(f"- **Total runtime:** {total_time:.0f}s")
    if verify_result:
        v_status = "PASS" if verify_result["success"] else "FAIL"
        lines.append(f"- **Verification pass:** {v_status} ({verify_result['duration']:.0f}s)")
    lines.append("")

    # Results table
    lines.append("## Investigation Results")
    lines.append("")
    lines.append("| # | Topic | Tier | Status | Time | Report |")
    lines.append("|---|-------|------|--------|------|--------|")
    for r in results:
        status = "OK" if r["success"] else "FAILED"
        report_link = r["output"] if r["success"] else "N/A"
        lines.append(
            f"| {r['id']} | {r['topic']} | {r['tier']} | {status} | {r['duration']:.0f}s | {report_link} |"
        )
    lines.append("")

    # Failed details
    if failed > 0:
        lines.append("## Failures")
        lines.append("")
        for r in results:
            if not r["success"]:
                lines.append(f"### {r['id']} - {r['topic']}")
                lines.append(f"```\n{r.get('error', 'Unknown')}\n```")
                lines.append("")

    # Per-investigation summaries
    lines.append("## Investigation Summaries")
    lines.append("")
    for r in results:
        lines.append(f"### {r['id']} - {r['topic']}")
        lines.append("")
        if r["success"]:
            summary = read_report_summary(r["output"])
            lines.append(summary)
        else:
            lines.append(f"*Failed to run.* Error: {r.get('error', 'Unknown')}")
        lines.append("")

    # Verification summary
    if verify_result:
        lines.append("## Verification Pass")
        lines.append("")
        if verify_result["success"]:
            summary = read_report_summary(VERIFICATION["output"])
            lines.append(summary)
        else:
            lines.append(f"*Verification failed.* Error: {verify_result.get('error', 'Unknown')}")
        lines.append("")

    # Decision implications
    lines.append("## Decision Implications")
    lines.append("")
    lines.append("Depending on findings, these investigations may trigger:")
    lines.append("- **I20**: If corporate hierarchy covers <5% of F7, may need to reduce Factor 1 (union proximity) weight from 3x")
    lines.append("- **I17**: If distribution is still bimodal, more scoring work needed before Phase 4/6")
    lines.append("- **I12**: If geographic bias is severe, geographic normalization needed in scoring")
    lines.append("- **I19**: If Mel-Ro false positive rate is high, many-to-one inflation is systematic")
    lines.append("- **I15/I14**: If legacy match quality is poor, re-running matching pipeline with stricter floors is warranted")
    lines.append("")

    # Write
    os.makedirs(INVESTIGATIONS_DIR, exist_ok=True)
    output_path = os.path.join(INVESTIGATIONS_DIR, "PHASE_1B_SUMMARY.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote consolidated summary: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Phase 1B Investigation Sprint Runner")
    parser.add_argument("--all", action="store_true", help="Run all investigations + verification")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], help="Run only a specific tier")
    parser.add_argument("--only", nargs="+", help="Run only specific investigations (e.g., I11 I17)")
    parser.add_argument("--verify-only", action="store_true", help="Run only the verification pass")
    parser.add_argument("--no-verify", action="store_true", help="Skip verification pass")
    parser.add_argument("--no-summary", action="store_true", help="Skip consolidated summary generation")
    args = parser.parse_args()

    if not any([args.all, args.tier, args.only, args.verify_only]):
        parser.print_help()
        print("\nExample: py scripts/analysis/run_phase_1b.py --all")
        sys.exit(1)

    # Determine which investigations to run
    to_run = []
    if args.all:
        to_run = list(INVESTIGATIONS)
    elif args.tier:
        to_run = [inv for inv in INVESTIGATIONS if inv["tier"] == args.tier]
    elif args.only:
        ids = {x.upper() for x in args.only}
        to_run = [inv for inv in INVESTIGATIONS if inv["id"] in ids]
        missing = ids - {inv["id"] for inv in to_run}
        if missing:
            print(f"Warning: Unknown investigation IDs: {missing}")

    run_verify = args.all or args.verify_only

    # Execute investigations
    results = []
    for inv in to_run:
        print(f"\n{'='*60}")
        print(f"Running {inv['id']}: {inv['topic']} (Tier {inv['tier']})")
        print(f"{'='*60}")
        success, duration, error = run_script(inv, PROJECT_ROOT)
        status = "OK" if success else "FAILED"
        print(f"  -> {status} ({duration:.1f}s)")
        if error:
            print(f"  -> Error: {error[:200]}")
        results.append({
            "id": inv["id"],
            "topic": inv["topic"],
            "tier": inv["tier"],
            "output": inv["output"],
            "success": success,
            "duration": duration,
            "error": error,
        })

    # Verification pass
    verify_result = None
    if run_verify and not args.no_verify:
        print(f"\n{'='*60}")
        print("Running Verification Pass")
        print(f"{'='*60}")
        success, duration, error = run_script(VERIFICATION, PROJECT_ROOT)
        status = "OK" if success else "FAILED"
        print(f"  -> {status} ({duration:.1f}s)")
        if error:
            print(f"  -> Error: {error[:200]}")
        verify_result = {
            "success": success,
            "duration": duration,
            "error": error,
        }

    # Generate consolidated summary
    if not args.no_summary and (results or verify_result):
        print(f"\n{'='*60}")
        print("Generating Consolidated Summary")
        print(f"{'='*60}")
        generate_consolidated_summary(results, verify_result)

    # Final summary
    print(f"\n{'='*60}")
    print("PHASE 1B COMPLETE")
    print(f"{'='*60}")
    succeeded = sum(1 for r in results if r["success"])
    failed = sum(1 for r in results if not r["success"])
    print(f"Investigations: {succeeded} passed, {failed} failed out of {len(results)}")
    if verify_result:
        print(f"Verification: {'PASS' if verify_result['success'] else 'FAIL'}")

    # Exit with error if any failures
    if failed > 0 or (verify_result and not verify_result["success"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
