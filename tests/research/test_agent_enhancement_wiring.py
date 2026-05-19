"""Tests for the score enhancement wiring at the end of _run_agent_loop.

Confirms the single-run path now calls compute_research_enhancements() under
the same dual-gate that batch_research.py uses (overall_quality_score >= 6.0
and employer_id is set). This is a structural test that reads the agent.py
source -- we cannot exercise the full _run_agent_loop() without a live Gemini
key, but we can guarantee the wiring exists and references the right
guards.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT))

_AGENT_PATH = _PROJECT / "scripts" / "research" / "agent.py"


def _read_agent_source() -> str:
    return _AGENT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Wiring presence
# ---------------------------------------------------------------------------


class TestEnhancementWiring:
    """The single-run path (_run_agent_loop) must call enhancement explicitly.

    These tests guard against a future refactor that removes the wiring and
    silently regresses the single-run path back to the pre-2026-05-12 state
    where only batch_research.py produced enhancement rows.
    """

    def test_compute_research_enhancements_imported_in_agent(self):
        src = _read_agent_source()
        assert "from scripts.research.auto_grader import compute_research_enhancements" in src

    def test_enhancement_called_after_grade_and_save(self):
        # Order matters: grade_and_save must run first because the gate
        # depends on overall_quality_score being persisted.
        src = _read_agent_source()
        grade_idx = src.find("grade_and_save(run_id)")
        enh_idx = src.find("compute_research_enhancements(run_id)")
        assert grade_idx > 0, "grade_and_save call not found"
        assert enh_idx > 0, "compute_research_enhancements call not found"
        assert enh_idx > grade_idx, (
            "compute_research_enhancements must be called AFTER grade_and_save"
        )

    def test_dual_gate_threshold_is_6_0(self):
        # The gate threshold (>= 6.0) must match the one inside
        # compute_research_enhancements() itself, otherwise we would either
        # double-skip or attempt enhancements that will be silently dropped.
        src = _read_agent_source()
        # Find the gate check near the enhancement call -- regex tolerates
        # whitespace and either `overall_score` or `overall` as the var name.
        # Match the form: if <var> >= 6.0 and run.get("employer_id"):
        m = re.search(
            r"if\s+\w+\s*>=\s*6\.0\s+and\s+run\.get\([\"']employer_id[\"']\)\s*:",
            src,
        )
        assert m is not None, "Expected `if <var> >= 6.0 and run.get('employer_id'):` gate"

    def test_enhancement_wrapped_in_try_except(self):
        # The enhancement call must not raise out of the agent loop -- a
        # failure to compute enhancement should not mark the run as failed.
        src = _read_agent_source()
        # Find the function call and walk back to confirm it's inside try:.
        call_idx = src.find("compute_research_enhancements(run_id)")
        assert call_idx > 0
        prefix = src[:call_idx]
        # The most recent 'try:' before the call should not be preceded by a
        # 'return' or 'def' that would close the function scope.
        last_try = prefix.rfind("try:")
        last_def = prefix.rfind("def ")
        assert last_try > 0
        assert last_try > last_def, "compute_research_enhancements call not inside a try block"

    def test_grade_result_used_to_avoid_extra_db_round_trip(self):
        # The optimisation in the wiring is: read overall_quality_score from
        # the grade_and_save return value rather than re-querying the DB.
        # Guard against a future refactor that re-introduces a SELECT.
        src = _read_agent_source()
        # We want to see `grade_result = grade_and_save(...)` assignment
        assert "grade_result = grade_and_save(run_id)" in src
        # And the gate should consult grade_result, not a fresh SELECT
        assert ".get(\"overall\"" in src or ".get('overall'" in src


# ---------------------------------------------------------------------------
# Sanity: the rest of the auto-grade pipeline is still wired
# ---------------------------------------------------------------------------


class TestExistingPipelineStillWired:
    """Defensive: ensure my edit did not break the other phases that already
    existed (contradiction detection, validation, strategy update). These are
    listed in CLAUDE.md as the correctness pillars of the research agent.
    """

    def test_contradiction_detection_still_called(self):
        src = _read_agent_source()
        assert "_resolve_contradictions(run_id)" in src

    def test_cross_run_contradictions_still_called(self):
        src = _read_agent_source()
        assert "_resolve_cross_run_contradictions(" in src

    def test_validation_still_called(self):
        src = _read_agent_source()
        assert "from scripts.research.report_validation import validate_dossier" in src

    def test_strategy_update_still_called(self):
        src = _read_agent_source()
        assert "update_strategy_quality()" in src
