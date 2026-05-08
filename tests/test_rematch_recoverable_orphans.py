"""Tests for the F7 orphan rematch executor (dry-run mode).

The executor is gated: --commit is the ONLY path that writes, and it
requires interactive 'yes' confirmation. These tests cover the dry-run
behavior (the read-only path Jacob will use to review thresholds) and
the gate (no writes happen unless --commit is set).
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

from db_config import get_connection


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "matching" / "rematch_recoverable_orphans.py"


def _has_staging_table() -> bool:
    """The staging table is created by identify_recoverable_orphans.py.
    These tests skip cleanly if it's not present (CI / fresh DB)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('_recoverable_f7_orphans')")
        if not cur.fetchone()[0]:
            return False
        cur.execute("SELECT COUNT(*) FROM _recoverable_f7_orphans")
        n = cur.fetchone()[0]
        conn.close()
        return n > 0
    except Exception:
        return False


# Per-test skip decorator for tests that need the orphan staging table
# (subprocess-based dry-run tests). The unit tests at the bottom of the
# file (rule engine helpers) do NOT need the table and run unconditionally.
_skip_no_staging = pytest.mark.skipif(
    not _has_staging_table(),
    reason="_recoverable_f7_orphans staging not present",
)


def _uml_count() -> int:
    """Total active rows in unified_match_log targeting f7 system."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM unified_match_log "
        "WHERE target_system = 'f7' AND status = 'active'"
    )
    n = cur.fetchone()[0]
    conn.close()
    return n


@_skip_no_staging
def test_dry_run_writes_nothing_to_unified_match_log(tmp_path):
    """The default invocation (no --commit) MUST NOT touch UML at all."""
    csv_out = tmp_path / "rematch.csv"
    before = _uml_count()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--limit", "200", "--out-csv", str(csv_out)],
        capture_output=True, text=True, timeout=120,
    )
    after = _uml_count()
    assert proc.returncode == 0, f"dry-run failed: {proc.stderr[:500]}"
    assert before == after, (
        f"DRY-RUN WROTE TO unified_match_log!  before={before} after={after}"
    )


@_skip_no_staging
def test_dry_run_emits_csv_with_expected_columns(tmp_path):
    """CSV output is the artifact Jacob will review. Lock its columns.

    Schema as of 2026-05-08 (B.3.x Option C): the original 8 columns
    stayed at the front (back-compat) and 3 rule_engine_* columns were
    APPENDED at the end. Older parsers that only read the first 8
    cols still work.
    """
    csv_out = tmp_path / "rematch.csv"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--limit", "500", "--out-csv", str(csv_out)],
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[:500]
    assert csv_out.exists()
    with open(csv_out, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Schema lock — these are the columns the review process will rely on
        assert reader.fieldnames == [
            "f7_employer_id", "f7_name", "f7_state",
            "source", "source_id", "source_name_norm",
            "method", "score",
            "rule_engine_tier", "rule_engine_rule", "rule_engine_precision",
        ]
        rows = list(reader)
    # At limit=500 we expect at least SOME matches across all 4 sources.
    assert len(rows) > 0, "no matches found at limit=500 — sanity check failed"
    valid_re_tiers = {
        "tier_A_auto_merge", "tier_B_high_conf",
        "tier_C_review", "tier_D_different",
        # tier_series_demoted is vetoed — should NOT appear in best-match CSV
    }
    for r in rows:
        assert r["source"] in {"osha", "whd", "990", "sam"}
        assert r["method"] in {
            "NAME_STANDARD_STATE_ZIP_EXACT",
            "NAME_STANDARD_STATE_EXACT",
            "NAME_AGGRESSIVE_STATE_EXACT",
        }
        # Score floor 0.91 — rule engine UPGRADES tier_B to 0.91, tier_A
        # to 0.96. Otherwise the SQL minimum is 0.92 (NAME_AGGRESSIVE).
        assert 0.91 <= float(r["score"]) <= 1.0
        assert r["rule_engine_tier"] in valid_re_tiers, (
            f"unexpected rule_engine_tier: {r['rule_engine_tier']}"
        )
        # Vetoed matches MUST NOT appear in the best-match CSV
        assert r["rule_engine_tier"] != "tier_series_demoted"


@_skip_no_staging
def test_dry_run_summary_includes_per_source_breakdown(tmp_path):
    """The stdout summary is what surfaces in screen-share / handoff
    docs — make sure it carries the per-source counts."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--limit", "300"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[:500]
    out = proc.stdout
    assert "SUMMARY" in out
    # Each of 4 sources should appear in the breakdown
    for src in ("osha", "whd", "990", "sam"):
        assert src in out, f"summary missing {src}"
    # Score distribution section
    assert "Score distribution" in out


@_skip_no_staging
def test_dry_run_matches_are_state_consistent(tmp_path):
    """No match should pair an F7 in one state with a source record in
    another. State-mismatch indicates a regression in the SQL where
    clause."""
    csv_out = tmp_path / "rematch.csv"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--limit", "500", "--out-csv", str(csv_out)],
        capture_output=True, text=True, timeout=120,
    )
    # Cross-check: pull the f7 + source rows for each CSV match.
    conn = get_connection()
    cur = conn.cursor()
    state_map = {
        "osha":  ("osha_establishments", "establishment_id", "site_state"),
        "whd":   ("whd_cases",           "case_id",          "state"),
        "990":   ("national_990_filers", "ein",              "state"),
        "sam":   ("sam_entities",        "uei",              "physical_state"),
    }
    with open(csv_out, encoding="utf-8") as f:
        for r in list(csv.DictReader(f))[:50]:
            tbl, idcol, statecol = state_map[r["source"]]
            cur.execute(
                f"SELECT {statecol} FROM {tbl} WHERE {idcol} = %s LIMIT 1",
                [r["source_id"]],
            )
            row = cur.fetchone()
            if row is None:
                continue
            src_state = row[0] if isinstance(row, tuple) else row[statecol]
            assert src_state == r["f7_state"], (
                f"state mismatch: f7={r['f7_state']} src={src_state} "
                f"on {r['source']}/{r['source_id']}"
            )
    conn.close()


@_skip_no_staging
def test_commit_flag_does_not_short_circuit_confirmation(tmp_path):
    """--commit alone (no piped 'yes') must not write. The script
    prompts interactively, and an empty stdin returns EOF → script
    aborts. This is the key safety property of the gate."""
    before = _uml_count()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--limit", "100", "--commit", "--min-score", "1.00"],
        capture_output=True, text=True, timeout=120,
        input="",  # empty stdin — confirmation prompt sees EOF
    )
    after = _uml_count()
    assert before == after, "EMPTY-STDIN --commit MUST NOT write to UML"
    # Script should explicitly say "Aborted." when it doesn't get yes
    assert "Aborted" in proc.stdout or "Aborted" in proc.stderr or proc.returncode != 0


# ---------------------------------------------------------------------------
# Rule engine integration unit tests (B.3.x Option C, 2026-05-08)
#
# These don't need the staging table — they test the in-process helpers
# (`_build_rule_engine_pair`, `classify_with_rule_engine`) directly, so
# they survive on a fresh DB / CI without the orphan staging present.
# Bypass the module-level skipif by using a separate decorator.
# ---------------------------------------------------------------------------

# Override module-level skipif for these unit tests — they don't read DB
_unit_test_marker = pytest.mark.usefixtures()  # no fixture; placeholder


def _import_rematch():
    """Import the rematch module fresh so the helpers are accessible
    without going through subprocess. Adds repo root to sys.path."""
    import importlib
    import sys as _sys
    repo = REPO_ROOT
    if str(repo) not in _sys.path:
        _sys.path.insert(0, str(repo))
    return importlib.import_module("scripts.matching.rematch_recoverable_orphans")


def test_rule_engine_vetoes_h4_series_fragment():
    """Rule engine VETO path: a candidate where both names are
    'XYZ INC SERIES n' differing only by trailing series identifier
    — H4 fires, classification is tier_series_demoted, the run_dry_run
    loop will drop the match.

    Uses 5-token names so the person_name_block predicate (which only
    fires on exactly 3 tokens with a 1-char last token) doesn't pre-empt
    H4 — they are different vetoes for different shapes.
    """
    rematch = _import_rematch()
    match = {
        "f7_employer_id": "f7_test_h4",
        "f7_name":        "Acme Industries Holdings Series 1",
        "f7_state":       "NY",
        "f7_zip":         "10001",
        "f7_city":        "New York",
        "source":         "osha",
        "source_id":      "osha_999",
        "source_name_norm": "acme industries holdings series 2",
        "source_zip":     "10001",
        "source_display": "Acme Industries Holdings Series 2",
        "source_city":    "New York",
        "source_ein":     None,
        "method":         "NAME_AGGRESSIVE_STATE_EXACT",
        "score":          0.92,
    }
    out = rematch.classify_with_rule_engine(match)
    assert out["rule_engine_tier"] == "tier_series_demoted"
    assert out["rule_engine_rule"] == "H4"
    assert out["rule_engine_precision"] == 1.00
    # Score not upgraded for vetoes — the run loop drops them outright
    assert out["score"] == 0.92


def test_rule_engine_vetoes_person_name_false_sibling():
    """Rule engine VETO path: 3-token names like 'WILLIAMS JAMES K' vs
    'WILLIAMS JAMES P' get falsely H4-clustered as siblings of a
    'WILLIAMS JAMES' parent — but they're DIFFERENT PEOPLE, never the
    same employer. The person_name_block predicate catches these
    before any H-rule fires."""
    rematch = _import_rematch()
    match = {
        "f7_employer_id": "f7_person_test",
        "f7_name":        "Williams James K",
        "f7_state":       "TX",
        "f7_zip":         None,
        "f7_city":        None,
        "source":         "whd",
        "source_id":      "whd_777",
        "source_name_norm": "williams james p",
        "source_zip":     None,
        "source_display": "Williams James P",
        "source_city":    None,
        "source_ein":     None,
        "method":         "NAME_AGGRESSIVE_STATE_EXACT",
        "score":          0.92,
    }
    out = rematch.classify_with_rule_engine(match)
    assert out["rule_engine_tier"] == "tier_series_demoted"
    assert out["rule_engine_rule"] == "person_name_block"


def test_rule_engine_upgrades_score_when_tier_a_fires():
    """Rule engine UPGRADE path: a NAME_AGGRESSIVE 0.92 match where
    H16 (source-diverse + city + zip + name match) fires gets its
    score lifted to 0.96 (tier_A precision floor). This is how the
    rule engine's higher-precision verdicts feed back into the score
    that gates --commit's --min-score filter."""
    rematch = _import_rematch()
    match = {
        "f7_employer_id": "f7_upgrade_test",
        "f7_name":        "Acme Industries Inc",
        "f7_state":       "CA",
        "f7_zip":         "90210",
        "f7_city":        "Beverly Hills",
        "source":         "osha",
        "source_id":      "osha_555",
        "source_name_norm": "acme industries",
        "source_zip":     "90210",
        # Punctuation-invariant identical name + same city + same zip +
        # different sources -> H16 fires -> tier_A
        "source_display": "Acme Industries, Inc.",
        "source_city":    "Beverly Hills",
        "source_ein":     None,
        "method":         "NAME_AGGRESSIVE_STATE_EXACT",
        "score":          0.92,
    }
    out = rematch.classify_with_rule_engine(match)
    assert out["rule_engine_tier"] == "tier_A_auto_merge"
    # Score lifted from 0.92 to at least 0.96
    assert out["score"] >= 0.96


def test_rule_engine_keeps_tier_d_at_sql_score():
    """tier_D_different = no rule fired. We KEEP these (the SQL
    exact-name match is still strong evidence), but the score stays
    at the SQL-assigned floor — no upgrade. This is the "rule engine
    is silent" path; most matches that don't have address corroboration
    land here."""
    rematch = _import_rematch()
    # Construct a pair the rule engine WON'T match: very short names
    # that fail H1/H2's len>=4 floor and have no zip5_match.
    match = {
        "f7_employer_id": "f7_short",
        "f7_name":        "ABC",
        "f7_state":       "FL",
        "f7_zip":         None,
        "f7_city":        None,
        "source":         "osha",
        "source_id":      "osha_111",
        "source_name_norm": "abc",
        "source_zip":     None,
        "source_display": "ABC",
        "source_city":    None,
        "source_ein":     None,
        "method":         "NAME_STANDARD_STATE_EXACT",
        "score":          0.98,
    }
    out = rematch.classify_with_rule_engine(match)
    # H1 fires at any length when names match exactly post-punct-strip.
    # That's tier_C (residual standalone H1) — still kept, no upgrade.
    assert out["rule_engine_tier"] in {"tier_C_review", "tier_D_different"}
    assert out["score"] == 0.98  # SQL score preserved (no upgrade for C/D)


def test_build_rule_engine_pair_zip5_match_logic():
    """The pair-builder must compute zip5_match correctly: 1.0 only
    when both 5-digit zips agree, 0.0 when one is missing or differs.
    Many ZIP-required rules (H6, H9, H11, H15, H16) gate on this."""
    rematch = _import_rematch()
    base = {
        "f7_name": "X", "source_display": "X", "source": "osha",
        "method": "NAME_STANDARD_STATE_EXACT",
    }
    # Both zips present and identical at zip5
    p = rematch._build_rule_engine_pair(
        {**base, "f7_zip": "12345", "source_zip": "12345"}
    )
    assert p["zip5_match"] == 1.0
    # ZIP+4 form on one side, 5-digit on the other — should still match
    p = rematch._build_rule_engine_pair(
        {**base, "f7_zip": "12345-6789", "source_zip": "12345"}
    )
    assert p["zip5_match"] == 1.0
    # Different zips
    p = rematch._build_rule_engine_pair(
        {**base, "f7_zip": "12345", "source_zip": "67890"}
    )
    assert p["zip5_match"] == 0.0
    # Missing zip on one side
    p = rematch._build_rule_engine_pair(
        {**base, "f7_zip": None, "source_zip": "12345"}
    )
    assert p["zip5_match"] == 0.0


def test_build_rule_engine_pair_sets_cross_source_labels():
    """source_1='f7' and source_2='<source-key>' must always differ.
    This is what makes H3 (cross-source corroboration) eligible — the
    rule engine guards on s1 != s2, so getting these wrong would
    silently disable H3, H14, H16."""
    rematch = _import_rematch()
    p = rematch._build_rule_engine_pair({
        "f7_name": "X", "source_display": "X",
        "source": "osha", "method": "NAME_STANDARD_STATE_EXACT",
        "f7_zip": None, "source_zip": None,
    })
    assert p["source_1"] == "f7"
    assert p["source_2"] == "osha"
    assert p["source_1"] != p["source_2"]


def test_build_rule_engine_pair_f7_has_no_ein():
    """F7 doesn't carry EIN. The pair-builder hardcodes ein_1=None and
    ein_match=0/ein_conflict=0 so neither H13 (EIN-match-alone) nor
    the EIN-conflict veto can fire spuriously."""
    rematch = _import_rematch()
    p = rematch._build_rule_engine_pair({
        "f7_name": "X", "source_display": "X",
        "source": "990", "method": "NAME_STANDARD_STATE_EXACT",
        "f7_zip": "12345", "source_zip": "12345",
        "source_ein": "12-3456789",
    })
    assert p["ein_1"] is None
    assert p["ein_2"] == "12-3456789"
    assert p["ein_match"] == 0
    assert p["ein_conflict"] == 0


@_skip_no_staging
def test_no_rule_engine_flag_skips_classification(tmp_path):
    """--no-rule-engine reproduces the 2026-05-06 dry-run shape (no
    rule_engine_* tags applied). Used for diff-against-baseline
    validation and emergency rollback."""
    csv_out = tmp_path / "rematch.csv"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--limit", "200",
         "--no-rule-engine", "--out-csv", str(csv_out)],
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[:500]
    assert "Rule engine: SKIPPED" in proc.stdout
    # CSV columns include the rule_engine_* fields but they're empty
    with open(csv_out, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) > 0
    for r in rows:
        # Rule engine fields are absent from the dict (DictWriter writes
        # them as empty strings since extrasaction='ignore' + the rows
        # don't contain those keys).
        assert r["rule_engine_tier"] == ""
        assert r["rule_engine_rule"] == ""
