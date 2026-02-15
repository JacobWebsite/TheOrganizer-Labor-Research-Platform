"""
Static regression guards for recently patched innerHTML/XSS paths.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_detail_projection_header_uses_sanitized_matrix_code():
    text = _read("files/js/detail.js")
    assert "const matrixCode = escapeHtml(String(data.matrix_code || ''));" in text
    assert "(${matrixCode})" in text


def test_detail_projection_toggle_uses_numeric_occupation_count():
    text = _read("files/js/detail.js")
    assert "const occupationCount = Number(data.occupation_count) || 0;" in text
    assert "(${occupationCount} jobs)" in text


def test_modals_corporate_summary_uses_precomputed_numeric_displays():
    text = _read("files/js/modal-corporate.js")
    assert "const totalFamilyDisplay = Number(data.total_family) || 0;" in text
    assert "const totalWorkersDisplay = formatNumber(Number(data.total_workers) || 0);" in text
    assert "const statesCountDisplay = Array.isArray(data.states) ? data.states.length : 0;" in text


def test_modals_unified_detail_uses_safe_source_fields():
    text = _read("files/js/modal-unified.js")
    assert "const safeSourceType = escapeHtml(String(detail.source_type || 'N/A'));" in text
    assert "const safeSourceId = escapeHtml(String(detail.source_id || 'N/A'));" in text
    assert "${safeSourceType}" in text
    assert "${safeSourceId}" in text


def test_scorecard_sector_stats_use_sanitized_sector_and_numeric_counts():
    text = _read("files/js/scorecard.js")
    assert "const safeSector = escapeHtml(String(data.sector || ''));" in text
    assert "const targetCount = Number(data.targets?.target_count) || 0;" in text
    assert "const unionizedCount = Number(data.unionized?.unionized_count) || 0;" in text
    assert "const densityPct = Number(data.union_density_pct) || 0;" in text


def test_scorecard_detail_uses_precomputed_nlrb_description():
    text = _read("files/js/scorecard.js")
    assert "const predictedWinPct = Number(detail.nlrb_context?.predicted_win_pct);" in text
    assert "const nlrbDescription = Number.isFinite(predictedWinPct)" in text
    assert "renderScoreRow('NLRB Patterns', breakdown.nlrb, 10, 'bg-green-500', nlrbDescription)" in text

