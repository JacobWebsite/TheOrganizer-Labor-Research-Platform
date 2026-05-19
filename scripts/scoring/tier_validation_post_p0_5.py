"""
Tier Validation against NLRB Outcomes (post-P0 #5 split).

Validates that the redrawn tier definitions in mv_unified_scorecard
correlate with empirical NLRB-organizing-activity. The closest proxy we
have for "would this employer be a successful organizing target" is
historical NLRB filing density on that employer (elections + ULPs).

Read-only. Does not REFRESH or modify any MV.

Background
----------
On 2026-05-06 (commit eb05a8e), the old `Promising` tier was split into
two:
  - `Promising` (kept): 60-84 percentile WITH at least one direct factor
    (OSHA / NLRB / WHD / contracts / financial). Real signals.
  - `Speculative` (new): 85+ percentile but ZERO direct factors -- the
    thin-data 87% subset that was inflating Promising. Modeled-signal
    only (similarity / size / industry growth / union proximity).

Pre-fix, Promising had 9.8% enforcement rate while Low had 61% -- a
reversal that the audit flagged as the largest scoring-quality issue.
Post-fix, the roadmap claims Promising went to 71.5% enforcement.

This script computes the empirical event rates per tier so we can
confirm the new ordering empirically:
    expected: Priority > Strong > Promising > Speculative > Moderate > Low
            (or, more practically, the *tier order* should monotonically
             relate to NLRB activity rates)

Outputs
-------
Prints a markdown report to stdout. The caller is expected to capture it
into a docs/scratch/<name>.md file.

Usage
-----
    py scripts/scoring/tier_validation_post_p0_5.py
    py scripts/scoring/tier_validation_post_p0_5.py > docs/scratch/tier_validation_post_eb05a8e.md
"""
from __future__ import annotations

import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection


TIER_ORDER = ["Priority", "Strong", "Promising", "Speculative", "Moderate", "Low"]

# Expected ordering: monotonically decreasing NLRB activity from top tier
# to bottom. P0 #5 promised the Promising/Speculative split would untangle
# the inversion that put Low above Promising on enforcement rate.
EXPECTED_PRIMARY_ORDER = ["Priority", "Strong", "Promising", "Speculative", "Moderate", "Low"]


def fetch_tier_metrics(cur):
    """
    Compute per-tier NLRB outcome metrics from mv_unified_scorecard.

    The MV already pre-aggregates NLRB elections and ULPs at the F7
    employer level (nlrb_election_count, nlrb_win_count, nlrb_ulp_count,
    has_recent_violations).

    Returns a list of dicts keyed by tier with:
      - n: total employers in tier
      - pct_with_election: % with >=1 NLRB election ever
      - pct_with_ulp: % with >=1 ULP charge ever
      - pct_with_recent_viol: % with has_recent_violations=TRUE
      - pct_with_active_contracts: % with has_active_contracts=TRUE
      - mean_elections: avg election_count per employer
      - mean_wins: avg win_count per employer
      - mean_ulps: avg ulp_count per employer
      - pct_with_any_nlrb: % with any NLRB activity (election OR ULP)
    """
    cur.execute("""
    SELECT
        score_tier,
        COUNT(*) AS n,
        SUM(CASE WHEN COALESCE(nlrb_election_count, 0) > 0 THEN 1 ELSE 0 END) AS n_with_election,
        SUM(CASE WHEN COALESCE(nlrb_ulp_count, 0) > 0 THEN 1 ELSE 0 END) AS n_with_ulp,
        SUM(CASE WHEN has_recent_violations THEN 1 ELSE 0 END) AS n_with_recent_viol,
        SUM(CASE WHEN has_active_contracts THEN 1 ELSE 0 END) AS n_with_active_contracts,
        SUM(CASE WHEN COALESCE(nlrb_election_count, 0) > 0
                   OR COALESCE(nlrb_ulp_count, 0) > 0
                 THEN 1 ELSE 0 END) AS n_with_any_nlrb,
        AVG(COALESCE(nlrb_election_count, 0))::numeric(10,4) AS mean_elections,
        AVG(COALESCE(nlrb_win_count, 0))::numeric(10,4)      AS mean_wins,
        AVG(COALESCE(nlrb_ulp_count, 0))::numeric(10,4)      AS mean_ulps,
        AVG(direct_factors_available)::numeric(10,2) AS mean_direct_factors,
        AVG(factors_available)::numeric(10,2) AS mean_factors
    FROM mv_unified_scorecard
    GROUP BY score_tier
    """)
    rows = cur.fetchall()
    by_tier = {}
    for (
        tier, n, n_election, n_ulp, n_recent, n_contracts, n_any_nlrb,
        mean_el, mean_w, mean_ulp, mean_direct, mean_total,
    ) in rows:
        n = int(n) if n else 0
        by_tier[tier] = {
            "tier": tier,
            "n": n,
            "n_election": int(n_election or 0),
            "n_ulp": int(n_ulp or 0),
            "n_recent_viol": int(n_recent or 0),
            "n_contracts": int(n_contracts or 0),
            "n_any_nlrb": int(n_any_nlrb or 0),
            "pct_election": (100.0 * (n_election or 0) / n) if n else 0.0,
            "pct_ulp": (100.0 * (n_ulp or 0) / n) if n else 0.0,
            "pct_recent_viol": (100.0 * (n_recent or 0) / n) if n else 0.0,
            "pct_contracts": (100.0 * (n_contracts or 0) / n) if n else 0.0,
            "pct_any_nlrb": (100.0 * (n_any_nlrb or 0) / n) if n else 0.0,
            "mean_elections": float(mean_el or 0),
            "mean_wins": float(mean_w or 0),
            "mean_ulps": float(mean_ulp or 0),
            "mean_direct_factors": float(mean_direct or 0),
            "mean_factors": float(mean_total or 0),
        }
    return by_tier


def fetch_election_outcome_rates(cur):
    """
    Among employers WITH at least one NLRB election, what is the
    union-win rate per tier? This is a stricter signal: of the
    organizing campaigns that actually happened, how many succeeded.
    """
    cur.execute("""
    SELECT
        score_tier,
        COUNT(*) FILTER (WHERE COALESCE(nlrb_election_count, 0) > 0) AS n_employers_with_elections,
        SUM(COALESCE(nlrb_election_count, 0)) AS total_elections,
        SUM(COALESCE(nlrb_win_count, 0)) AS total_wins
    FROM mv_unified_scorecard
    GROUP BY score_tier
    """)
    rows = cur.fetchall()
    by_tier = {}
    for tier, n_emp, total_el, total_w in rows:
        n_emp = int(n_emp or 0)
        total_el = int(total_el or 0)
        total_w = int(total_w or 0)
        by_tier[tier] = {
            "n_employers_with_elections": n_emp,
            "total_elections": total_el,
            "total_wins": total_w,
            "win_rate": (100.0 * total_w / total_el) if total_el else 0.0,
        }
    return by_tier


def detect_inversions(metrics, key, expected_order=EXPECTED_PRIMARY_ORDER):
    """
    Walk the expected tier order and report any place where the metric
    is higher in a lower-ranked tier than its predecessor. Returns a
    list of (higher_tier, lower_tier, higher_val, lower_val) tuples
    where lower_tier should have been < higher_tier on `key`.
    """
    inversions = []
    series = []
    for t in expected_order:
        if t in metrics:
            series.append((t, metrics[t].get(key, 0.0)))
    # Compare each adjacent pair
    for i in range(len(series) - 1):
        higher_tier, higher_val = series[i]
        lower_tier, lower_val = series[i + 1]
        if lower_val > higher_val:
            inversions.append((higher_tier, lower_tier, higher_val, lower_val))
    return inversions


def fetch_target_scorecard_summary(cur):
    """Brief gold_standard_tier distribution from mv_target_scorecard."""
    cur.execute("""
    SELECT gold_standard_tier, COUNT(*) AS n
    FROM mv_target_scorecard
    GROUP BY gold_standard_tier
    ORDER BY n DESC
    """)
    return [(t, int(n)) for t, n in cur.fetchall()]


def main():
    conn = get_connection()
    cur = conn.cursor()

    # Confirm the MV has the new Speculative tier (= P0 #5 shipped).
    cur.execute("SELECT COUNT(*) FROM mv_unified_scorecard WHERE score_tier = 'Speculative'")
    n_spec = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM mv_unified_scorecard")
    n_total = cur.fetchone()[0]

    metrics = fetch_tier_metrics(cur)
    outcomes = fetch_election_outcome_rates(cur)
    target_dist = fetch_target_scorecard_summary(cur)

    cur.close()
    conn.close()

    # --- Print a markdown report to stdout ----------------------------------
    out = []
    out.append("# Tier Validation against NLRB Outcomes (post-P0 #5 / commit eb05a8e)")
    out.append("")
    out.append(f"Generated: {datetime.datetime.now().isoformat(timespec='seconds')}")
    out.append("")
    out.append(f"`mv_unified_scorecard` rows: **{n_total:,}**.  ")
    out.append(f"`Speculative` tier present: **{'YES' if n_spec > 0 else 'NO'}** "
               f"({n_spec:,} rows).")
    out.append("")
    out.append("## Methodology")
    out.append("")
    out.append(
        "For each tier, we compute the share of employers with any NLRB "
        "activity (elections or ULPs), the share with elections, the share "
        "with ULPs, the share with `has_recent_violations` (rolling 2-year "
        "OSHA/NLRB/WHD signal), and means per employer. The expected "
        "ordering is monotonically decreasing top-to-bottom across the "
        "six tiers."
    )
    out.append("")
    out.append("## Tier Distribution")
    out.append("")
    out.append("| Tier | Count | % of Total | Mean Direct Factors | Mean Factors |")
    out.append("|------|------:|-----------:|--------------------:|-------------:|")
    for t in TIER_ORDER:
        m = metrics.get(t)
        if not m:
            out.append(f"| {t} | 0 | 0.0% | - | - |")
            continue
        pct = (100.0 * m["n"] / n_total) if n_total else 0.0
        out.append(
            f"| {t} | {m['n']:,} | {pct:.2f}% | "
            f"{m['mean_direct_factors']:.2f} | {m['mean_factors']:.2f} |"
        )
    out.append("")

    out.append("## NLRB Activity Rates by Tier")
    out.append("")
    out.append(
        "| Tier | n | % w/ Election | % w/ ULP | % w/ Any NLRB | % w/ Recent Violations | % w/ Active Contracts |"
    )
    out.append(
        "|------|--:|--------------:|---------:|--------------:|-----------------------:|----------------------:|"
    )
    for t in TIER_ORDER:
        m = metrics.get(t)
        if not m:
            continue
        out.append(
            f"| {t} | {m['n']:,} | {m['pct_election']:.2f}% | "
            f"{m['pct_ulp']:.2f}% | {m['pct_any_nlrb']:.2f}% | "
            f"{m['pct_recent_viol']:.2f}% | {m['pct_contracts']:.2f}% |"
        )
    out.append("")

    out.append("## Mean NLRB Counts per Employer (by tier)")
    out.append("")
    out.append("| Tier | Mean Elections | Mean Wins | Mean ULPs |")
    out.append("|------|---------------:|----------:|----------:|")
    for t in TIER_ORDER:
        m = metrics.get(t)
        if not m:
            continue
        out.append(
            f"| {t} | {m['mean_elections']:.4f} | "
            f"{m['mean_wins']:.4f} | {m['mean_ulps']:.4f} |"
        )
    out.append("")

    out.append("## Election Outcomes (where elections happened)")
    out.append("")
    out.append("Among employers that actually faced an NLRB election, what fraction did the union win?")
    out.append("")
    out.append("| Tier | Employers w/ Elections | Total Elections | Total Wins | Win Rate |")
    out.append("|------|----------------------:|----------------:|-----------:|---------:|")
    for t in TIER_ORDER:
        o = outcomes.get(t)
        if not o:
            continue
        out.append(
            f"| {t} | {o['n_employers_with_elections']:,} | "
            f"{o['total_elections']:,} | {o['total_wins']:,} | "
            f"{o['win_rate']:.2f}% |"
        )
    out.append("")

    # --- Inversion detection ---
    out.append("## Inversion Detection")
    out.append("")
    out.append(
        "An inversion occurs when a *lower* tier has a *higher* event "
        "rate than its predecessor in the expected order "
        f"(`{' > '.join(EXPECTED_PRIMARY_ORDER)}`)."
    )
    out.append("")

    inv_rows = []
    keys_to_check = [
        ("pct_any_nlrb", "% with any NLRB activity"),
        ("pct_election", "% with NLRB election"),
        ("pct_ulp", "% with ULP charge"),
        ("pct_recent_viol", "% with recent violations"),
        ("mean_elections", "mean elections per employer"),
        ("mean_ulps", "mean ULPs per employer"),
    ]
    for key, label in keys_to_check:
        invs = detect_inversions(metrics, key)
        if not invs:
            inv_rows.append((label, "none", "-", "-", "-"))
        else:
            for higher_t, lower_t, hv, lv in invs:
                inv_rows.append((
                    label,
                    f"{higher_t} -> {lower_t}",
                    f"{hv:.4f}" if isinstance(hv, float) and abs(hv) < 1 else f"{hv:.2f}",
                    f"{lv:.4f}" if isinstance(lv, float) and abs(lv) < 1 else f"{lv:.2f}",
                    f"+{(lv - hv):.4f}" if isinstance(lv, float) and abs(lv) < 1 else f"+{(lv - hv):.2f}",
                ))

    out.append("| Metric | Inversion (higher -> lower tier) | Higher tier value | Lower tier value | Delta |")
    out.append("|--------|----------------------------------|------------------:|-----------------:|------:|")
    for row in inv_rows:
        out.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} |")
    out.append("")

    # Headline finding
    primary_inversions = detect_inversions(metrics, "pct_any_nlrb")
    if primary_inversions:
        out.append(
            f"**Primary metric (% with any NLRB activity) has "
            f"{len(primary_inversions)} inversion(s).**"
        )
    else:
        out.append(
            "**Primary metric (% with any NLRB activity) is monotonically "
            "decreasing -- tier ordering holds up empirically.**"
        )
    out.append("")

    # --- Comparison to roadmap claim ---
    out.append("## Comparison to Roadmap Claim (P0 #5 change log entry)")
    out.append("")
    out.append(
        "The 2026-05-06 roadmap entry claimed: "
        "*'Promising enforcement rate 9.8% -> 71.5% (now actually higher than "
        "Strong, as intended). Audit-flagged Promising vs Low inversion gone.'*"
    )
    out.append("")
    out.append(
        "Here, the closest analogue to 'enforcement rate' is "
        "`% with recent violations` (rolling 2-year OSHA/NLRB/WHD union "
        "of has_recent_violations). The next closest is "
        "`% with any NLRB activity` (lifetime)."
    )
    out.append("")
    p = metrics.get("Promising", {})
    s = metrics.get("Speculative", {})
    st = metrics.get("Strong", {})
    lo = metrics.get("Low", {})
    out.append("| Tier | % w/ Recent Violations | % w/ Any NLRB |")
    out.append("|------|----------------------:|--------------:|")
    for t in ["Strong", "Promising", "Speculative", "Low"]:
        m = metrics.get(t, {})
        out.append(
            f"| {t} | {m.get('pct_recent_viol', 0):.2f}% | "
            f"{m.get('pct_any_nlrb', 0):.2f}% |"
        )
    out.append("")
    out.append(
        f"Delta: Promising recent-violation rate is "
        f"{p.get('pct_recent_viol', 0):.2f}% post-fix. "
        f"Low recent-violation rate is {lo.get('pct_recent_viol', 0):.2f}%. "
        f"Speculative recent-violation rate is "
        f"{s.get('pct_recent_viol', 0):.2f}%."
    )
    out.append("")
    if p.get("pct_recent_viol", 0) > lo.get("pct_recent_viol", 0):
        out.append("**The Promising vs Low inversion is RESOLVED.** Promising > Low on recent-violation rate.")
    else:
        out.append(
            f"**The Promising vs Low inversion is NOT resolved.** "
            f"Low ({lo.get('pct_recent_viol', 0):.2f}%) >= "
            f"Promising ({p.get('pct_recent_viol', 0):.2f}%)."
        )
    out.append("")

    # --- mv_target_scorecard sanity ---
    out.append("## mv_target_scorecard (parallel non-union pool) sanity")
    out.append("")
    out.append("| gold_standard_tier | n |")
    out.append("|--------------------|--:|")
    for tier, n in target_dist:
        out.append(f"| {tier or '(NULL)'} | {n:,} |")
    out.append("")

    # --- Final summary box ---
    out.append("## Summary")
    out.append("")
    out.append(
        "- **Speculative tier present**: " + ("YES" if n_spec > 0 else "NO")
    )
    out.append(
        f"- **Speculative is dominated by thin-data rows**: mean direct factors "
        f"= {s.get('mean_direct_factors', 0):.2f} "
        f"(by definition direct_factors=0 is the gate; non-zero appears only if a "
        f"row entered Speculative via `score_percentile >= 0.85` AND had factors_available < 3, "
        f"see SQL line 864)."
    )
    out.append(
        f"- **Promising direct factors**: mean = {p.get('mean_direct_factors', 0):.2f} "
        f"(by definition direct_factors_available >= 1 required for entry)."
    )

    primary_inversions = detect_inversions(metrics, "pct_any_nlrb")
    if not primary_inversions:
        out.append(
            f"- **Primary tier ordering empirically holds** on % with any "
            f"NLRB activity ({EXPECTED_PRIMARY_ORDER[0]} > "
            f"{EXPECTED_PRIMARY_ORDER[-1]} monotonically)."
        )
    else:
        out.append(
            f"- **Primary tier ordering has {len(primary_inversions)} "
            f"inversion(s)** on % with any NLRB activity:"
        )
        for higher, lower, hv, lv in primary_inversions:
            out.append(f"  - {higher} ({hv:.2f}%) < {lower} ({lv:.2f}%)")

    print("\n".join(out))


if __name__ == "__main__":
    main()
