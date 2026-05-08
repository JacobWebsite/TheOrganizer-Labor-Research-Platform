"""
Match NLRB participants from the nightly pull to `master_employers`
via name+state blocking + rule-engine post-filter (H1-H16).

Companion to `scripts/etl/nlrb_nightly_pull.py`. The nightly pull drops a
handoff JSON in `scripts/etl/_nlrb_nightly_handoff/` listing the newly-inserted
case numbers. This script:

1. Reads the most recent handoff file (or a specific --handoff PATH).
2. Queries `nlrb_participants` WHERE case_number IN (new) AND participant_type
   IN ('Employer', 'Charged Party') AND matched_employer_id IS NULL.
3. Pairs each against candidate `master_employers` via UPPER(name)+state
   exact-block, same pattern as
   `scripts/etl/contracts/match_state_local_contracts_to_masters.py`.
4. Post-filters each candidate with
   `scripts/llm_dedup/rule_engine.py::classify_pair_v2` (H1-H16).
5. Writes Tier A + Tier B matches to `unified_match_log`
   with source_system='nlrb', match_method='nightly_exact_name_state_rule_filtered'.
6. Updates `nlrb_participants.matched_employer_id` for convenience.

Tier A = rule engine expected_precision >= 0.95.
Tier B = 0.85 <= expected_precision < 0.95.
Tier C+ is left as a review queue (unpopulated -- humans decide).

Usage:
    py scripts/matching/match_nlrb_nightly_to_masters.py --latest-handoff --dry-run
    py scripts/matching/match_nlrb_nightly_to_masters.py --latest-handoff --commit
    py scripts/matching/match_nlrb_nightly_to_masters.py --handoff path/to/nightly_cases_2026...json --commit

Verification:
    SELECT COUNT(*) FROM unified_match_log
        WHERE source_system = 'nlrb'
          AND match_method = 'nightly_exact_name_state_rule_filtered'
          AND created_at > CURRENT_DATE - INTERVAL '48 hours';
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from db_config import get_connection
from scripts.llm_dedup.rule_engine import classify_pair_v2

_log = logging.getLogger("matching.nlrb_nightly")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

DEFAULT_HANDOFF_DIR = ROOT / "scripts" / "etl" / "_nlrb_nightly_handoff"


def _find_latest_handoff(handoff_dir: Path) -> Path | None:
    if not handoff_dir.exists():
        return None
    files = sorted(handoff_dir.glob("nightly_cases_*.json"))
    return files[-1] if files else None


def _load_handoff(handoff_path: Path) -> list[str]:
    with open(handoff_path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    return doc.get("case_numbers", [])


def match_and_write(case_numbers: list[str], commit: bool) -> dict:
    """For each new case number, match its Employer/Charged-Party participants
    to master_employers via exact-block + rule engine. Returns a summary.
    """
    if not case_numbers:
        _log.info("no new case numbers to match")
        return {"participants_considered": 0, "tier_a": 0, "tier_b": 0, "tier_c_plus": 0}

    conn = get_connection()
    conn.autocommit = False
    cur = conn.cursor()

    # Step 1: pull participants we need to try to match
    cur.execute("""
        SELECT id, case_number, participant_name, participant_type, city, state, zip
        FROM nlrb_participants
        WHERE case_number = ANY(%s)
          AND participant_type IN ('Employer', 'Charged Party')
          AND matched_employer_id IS NULL
          AND participant_name IS NOT NULL
          AND LENGTH(TRIM(participant_name)) > 3
    """, (case_numbers,))
    participants = cur.fetchall()
    _log.info("%d employer-side participants to match across %d cases",
              len(participants), len(case_numbers))

    tier_a = tier_b = tier_c_plus = 0

    for p in participants:
        p_id = p[0]
        case_num = p[1]
        raw_name = (p[2] or "").strip()
        raw_city = (p[4] or "").strip()
        raw_state = (p[5] or "").strip().upper() or None
        raw_zip5 = ((p[6] or "")[:5]).strip() or None

        # Quick-block against master_employers on UPPER(display_name) + state
        if raw_state:
            cur.execute("""
                SELECT master_id, canonical_name, display_name, city, state, zip, ein,
                       source_origin, data_quality_score, naics
                FROM master_employers
                WHERE UPPER(display_name) = UPPER(%s)
                  AND state = %s
                LIMIT 50
            """, (raw_name, raw_state))
        else:
            cur.execute("""
                SELECT master_id, canonical_name, display_name, city, state, zip, ein,
                       source_origin, data_quality_score, naics
                FROM master_employers
                WHERE UPPER(display_name) = UPPER(%s)
                LIMIT 50
            """, (raw_name,))
        candidates = cur.fetchall()

        if not candidates:
            tier_c_plus += 1
            continue

        # Rule-engine classify each pair using the flat-dict shape
        # classify_pair_v2 expects (see
        # scripts/etl/contracts/match_state_local_contracts_to_masters.py::_build_pair
        # for the reference template). NLRB participants don't carry EIN, so
        # ein_1/ein_match/ein_conflict are all 0.
        best_master = None
        best_cls = None
        for cand in candidates:
            (m_master_id, m_canonical, m_display, m_city, m_state, m_zip, m_ein,
             m_source, _m_quality, _m_naics) = cand
            m_zip5 = ((m_zip or "")[:5]).strip() or None
            zip5_match = 1.0 if raw_zip5 and m_zip5 and raw_zip5 == m_zip5 else 0.0

            pair = {
                "display_name_1": raw_name,
                "display_name_2": m_display,
                "canonical_name_1": raw_name,
                "canonical_name_2": m_canonical,
                "source_1": "nlrb",
                "source_2": (m_source or "").strip().lower() or "master",
                "zip_1": raw_zip5,
                "zip_2": m_zip5,
                "ein_1": None,
                "ein_2": (m_ein or "").strip() or None,
                "city_1": raw_city,
                "city_2": (m_city or "").strip(),
                # Exact-block guarantees normalized name match -> sim = 1.0
                "name_standard_sim": 1.0,
                "name_aggressive_sim": 1.0,
                "zip5_match": zip5_match,
                "ein_match": 0,     # NLRB side has no EIN to compare
                "ein_conflict": 0,
            }
            cls = classify_pair_v2(pair)
            if best_cls is None or (cls.expected_precision or 0) > (best_cls.expected_precision or 0):
                best_master, best_cls = cand, cls

        precision = float(best_cls.expected_precision or 0)
        tier = "A" if precision >= 0.95 else "B" if precision >= 0.85 else "C"
        if tier == "A":
            tier_a += 1
        elif tier == "B":
            tier_b += 1
        else:
            tier_c_plus += 1
            continue  # don't write tier C; leave for review

        # Write unified_match_log + update matched_employer_id.
        # Codex finding #3 (2026-04-24): the matching UNIT is
        # `nlrb_participants.id`, not `case_number`. A case with multiple
        # employer-side participants would otherwise collapse to the same
        # `source_id` row, which (a) breaks audit trail and (b) can be
        # silently dropped by ON CONFLICT DO NOTHING if a uniqueness
        # constraint exists downstream. We log participant.id as source_id
        # and stash case_number in match_method for human readability.
        cur.execute("""
            INSERT INTO unified_match_log
                (source_system, source_id, target_system, target_id,
                 match_method, match_tier, confidence_band, confidence_score)
            VALUES ('nlrb_participants', %s, 'master_employers', %s,
                    %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            str(p_id),
            str(best_master[0]),
            f"nightly_exact_name_state_rule_filtered:{case_num}",
            tier,
            "HIGH" if tier == "A" else "MEDIUM",
            round(precision, 4),
        ))
        cur.execute("""
            UPDATE nlrb_participants
            SET matched_employer_id = %s,
                match_confidence = %s,
                match_method = 'nightly_exact_name_state_rule_filtered'
            WHERE id = %s AND matched_employer_id IS NULL
        """, (str(best_master[0]), round(precision, 4), p_id))

    summary = {
        "participants_considered": len(participants),
        "tier_a": tier_a,
        "tier_b": tier_b,
        "tier_c_plus": tier_c_plus,
    }

    if commit:
        conn.commit()
    else:
        conn.rollback()

    conn.close()
    return summary


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--handoff", type=Path, help="Path to a specific nightly-handoff JSON.")
    g.add_argument("--latest-handoff", action="store_true", help="Use the most recent handoff JSON in the default dir.")
    ap.add_argument("--commit", action="store_true", help="Persist writes (default dry-run).")
    ap.add_argument("--dry-run", action="store_true", help="Alias for --commit omitted.")
    ap.add_argument("--handoff-dir", type=Path, default=DEFAULT_HANDOFF_DIR)
    args = ap.parse_args()

    if args.handoff:
        handoff_path = args.handoff
    elif args.latest_handoff:
        handoff_path = _find_latest_handoff(args.handoff_dir)
        if not handoff_path:
            _log.info("no handoff files found in %s; nothing to do", args.handoff_dir)
            return
    else:
        ap.error("either --handoff PATH or --latest-handoff is required")

    case_numbers = _load_handoff(handoff_path)
    _log.info("loaded %d case number(s) from %s", len(case_numbers), handoff_path)

    summary = match_and_write(case_numbers, commit=args.commit and not args.dry_run)
    _log.info("summary: %s", summary)


if __name__ == "__main__":
    main()
