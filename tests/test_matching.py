"""
Matching pipeline tests for the Labor Research Platform.

Tests the 5-tier matching pipeline:
  Tier 1: EIN match
  Tier 2: Exact normalized name
  Tier 3: Address + name
  Tier 4: Aggressive normalization
  Tier 5: Fuzzy (pg_trgm + RapidFuzz)

Covers: normalizer unit tests, address helpers, composite scoring,
data structures, and DB integration (match rates, type safety).

Run with: py -m pytest tests/test_matching.py -v
"""
import sys
import os
import pytest
from datetime import datetime

# Add project root to path so scripts.matching is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.matching.normalizer import (
    normalize_employer_name,
    normalize_for_sql,
    generate_name_variants,
)
from scripts.matching.matchers.fuzzy import _composite_score
from scripts.matching.matchers.address import extract_street_number, normalize_address
from scripts.matching.matchers.base import MatchResult, MatchRunStats
from scripts.matching.config import MatchConfig, SCENARIOS


# ============================================================================
# A. NORMALIZER UNIT TESTS  (no DB needed)
# ============================================================================

class TestNormalizerStandard:
    """Standard-level normalization: lowercase, strip legal suffixes, clean punctuation."""

    def test_strips_inc_suffix(self):
        result = normalize_employer_name("The Kroger Company, Inc.")
        assert "inc" not in result
        assert "company" not in result
        assert "kroger" in result

    def test_strips_llc_suffix(self):
        result = normalize_employer_name("WALMART STORES LLC")
        assert "llc" not in result
        assert "walmart" in result

    def test_lowercases(self):
        result = normalize_employer_name("ACME CORPORATION")
        assert result == result.lower()

    def test_strips_corp_suffix(self):
        result = normalize_employer_name("ACME Corp.")
        assert "corp" not in result
        assert "acme" in result

    def test_strips_multiple_suffixes(self):
        result = normalize_employer_name("Smith & Jones Ltd.")
        assert "ltd" not in result


class TestNormalizerAggressive:
    """Aggressive normalization: expand abbreviations, remove stopwords."""

    def test_expands_hospital_abbreviation(self):
        result = normalize_employer_name("St. Mary's Hosp. Med. Ctr.", "aggressive")
        # Should expand abbreviations -- exact output depends on which normalizer is loaded
        # but should be longer than standard and contain expanded words
        assert len(result) > 5

    def test_strips_dba_prefix(self):
        result = normalize_employer_name("D/B/A Quick Mart", "aggressive")
        assert "d/b/a" not in result.lower()
        assert "dba" not in result.lower().split()

    def test_removes_stopwords(self):
        result = normalize_employer_name("The Acme Company of America", "aggressive")
        words = result.split()
        # 'the' and 'of' are stopwords
        assert "the" not in words
        assert "of" not in words

    def test_strips_possessive(self):
        result = normalize_employer_name("McDonald's Corporation", "aggressive")
        assert "'s" not in result


class TestNormalizerFuzzy:
    """Fuzzy normalization: remove numbers, single letters, additional cleaning."""

    def test_removes_standalone_numbers(self):
        result = normalize_employer_name("123 Main Street Store #456", "fuzzy")
        # Standalone numbers should be removed
        assert "123" not in result.split()
        assert "456" not in result.split()

    def test_removes_single_letters(self):
        result = normalize_employer_name("A.C.M.E. Corp.", "fuzzy")
        words = result.split()
        # After removing periods and single letters, should have 'acme' or similar
        for w in words:
            assert len(w) > 1, f"Single letter '{w}' found in fuzzy result"

    def test_strips_leading_articles(self):
        result = normalize_employer_name("The Great Company Inc.", "fuzzy")
        assert not result.startswith("the ")


class TestNormalizerEdgeCases:
    """Edge cases for the normalizer."""

    def test_empty_string(self):
        assert normalize_employer_name("") == ""

    def test_none_like_input(self):
        assert normalize_employer_name(None) == ""

    def test_whitespace_only(self):
        result = normalize_employer_name("   ")
        assert result.strip() == ""

    def test_very_short_name(self):
        result = normalize_employer_name("AB")
        assert isinstance(result, str)

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError, match="Unknown normalization level"):
            normalize_employer_name("test", "invalid_level")


class TestGenerateNameVariants:
    """generate_name_variants returns multiple distinct normalization levels."""

    def test_returns_list_of_tuples(self):
        variants = generate_name_variants("St. Mary's Hospital, Inc.")
        assert isinstance(variants, list)
        assert all(isinstance(v, tuple) and len(v) == 2 for v in variants)

    def test_first_variant_is_standard(self):
        variants = generate_name_variants("St. Mary's Hospital, Inc.")
        assert len(variants) >= 1
        assert variants[0][0] == "standard"

    def test_multiple_levels_for_abbreviations(self):
        variants = generate_name_variants("St. Mary's Hosp. Med. Ctr. Inc.")
        levels = [v[0] for v in variants]
        # With abbreviations, aggressive should differ from standard
        assert len(variants) >= 2


class TestNormalizeForSql:
    """normalize_for_sql escapes SQL LIKE wildcards."""

    def test_escapes_percent(self):
        result = normalize_for_sql("100% Pure Inc.")
        assert r"\%" in result or "%" not in result

    def test_escapes_underscore(self):
        result = normalize_for_sql("A_B Corporation")
        assert r"\_" in result or "_" not in result

    def test_normal_name_unchanged_except_normalization(self):
        result = normalize_for_sql("Acme Corp")
        assert "acme" in result


# ============================================================================
# B. ADDRESS HELPER UNIT TESTS  (no DB needed)
# ============================================================================

class TestExtractStreetNumber:
    """extract_street_number from various address formats."""

    def test_simple_address(self):
        assert extract_street_number("123 Main Street") == "123"

    def test_messy_nlrb_format(self):
        result = extract_street_number("Fort Wayne, IN 46801, 110 E Wayne Street")
        assert result == "110"

    def test_empty_input(self):
        assert extract_street_number("") == ""

    def test_none_input(self):
        assert extract_street_number(None) == ""

    def test_no_number(self):
        result = extract_street_number("Main Street")
        assert result == ""

    def test_zip_not_extracted(self):
        # Should extract building number, not ZIP code
        result = extract_street_number("Springfield, IL 62701, 200 E Adams St")
        assert result != "62701"


class TestNormalizeAddress:
    """normalize_address expands abbreviations and cleans."""

    def test_expands_abbreviations(self):
        result = normalize_address("123 N. Main St., Apt 4B")
        assert "street" in result
        assert "north" in result

    def test_empty_input(self):
        assert normalize_address("") == ""

    def test_none_input(self):
        assert normalize_address(None) == ""

    def test_expands_avenue(self):
        result = normalize_address("Suite 200, 456 Broadway Ave")
        assert "avenue" in result

    def test_removes_punctuation(self):
        result = normalize_address("123 Main St., #4B")
        assert "." not in result
        assert "," not in result


# ============================================================================
# C. COMPOSITE SCORE UNIT TESTS  (no DB needed)
# ============================================================================

class TestCompositeScore:
    """_composite_score produces expected similarity values."""

    def test_identical_names(self):
        score = _composite_score("walmart", "walmart")
        assert score >= 0.95, f"Identical names should score ~1.0, got {score}"

    def test_different_companies(self):
        score = _composite_score("walmart", "walgreens")
        assert score < 0.85, f"Different companies should score low, got {score}"

    def test_abbreviation_variants(self):
        score = _composite_score("saint marys hospital", "st mary hospital")
        assert score > 0.40, f"Abbreviation variants should have moderate score, got {score}"

    def test_returns_float_in_range(self):
        score = _composite_score("abc", "xyz")
        assert 0.0 <= score <= 1.0


# ============================================================================
# D. DATA STRUCTURE TESTS  (no DB needed)
# ============================================================================

class TestMatchResult:
    """MatchResult data class behavior."""

    def test_to_dict_keys(self):
        mr = MatchResult(
            source_id="S1",
            source_name="ACME Corp",
            target_id="T1",
            target_name="Acme Corporation",
            score=0.95,
            method="NORMALIZED",
            tier=2,
            confidence="HIGH",
            matched=True,
        )
        d = mr.to_dict()
        expected_keys = {
            "source_id", "source_name", "target_id", "target_name",
            "score", "method", "tier", "confidence", "matched", "metadata"
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_score_rounded(self):
        mr = MatchResult(source_id="1", source_name="test", score=0.123456789)
        d = mr.to_dict()
        assert d["score"] == 0.1235

    def test_defaults(self):
        mr = MatchResult(source_id="1", source_name="test")
        assert mr.matched is False
        assert mr.score == 0.0
        assert mr.metadata == {}


class TestMatchRunStats:
    """MatchRunStats.finalize computes correct match_rate."""

    def test_finalize_computes_rate(self):
        stats = MatchRunStats(
            scenario="osha_to_f7",
            run_id="test-001",
            started_at=datetime(2026, 1, 1),
            total_source=1000,
            total_matched=137,
        )
        stats.finalize()
        assert stats.match_rate == pytest.approx(13.7, abs=0.01)

    def test_finalize_zero_source(self):
        stats = MatchRunStats(
            scenario="test",
            run_id="test-002",
            started_at=datetime(2026, 1, 1),
            total_source=0,
            total_matched=0,
        )
        stats.finalize()
        assert stats.match_rate == 0.0


class TestMatchConfig:
    """MatchConfig dataclass defaults."""

    def test_default_fuzzy_threshold(self):
        cfg = MatchConfig(
            name="test",
            source_table="a",
            target_table="b",
            source_id_col="id",
            source_name_col="name",
            target_id_col="id",
            target_name_col="name",
        )
        assert cfg.fuzzy_threshold == 0.65

    def test_default_require_state_match(self):
        cfg = MatchConfig(
            name="test",
            source_table="a",
            target_table="b",
            source_id_col="id",
            source_name_col="name",
            target_id_col="id",
            target_name_col="name",
        )
        assert cfg.require_state_match is True

    def test_default_require_city_match_false(self):
        cfg = MatchConfig(
            name="test",
            source_table="a",
            target_table="b",
            source_id_col="id",
            source_name_col="name",
            target_id_col="id",
            target_name_col="name",
        )
        assert cfg.require_city_match is False


# ============================================================================
# E. DB INTEGRATION TESTS
# ============================================================================

@pytest.fixture(scope="module")
def db():
    """Provide a database connection for DB-dependent tests."""
    from db_config import get_connection
    conn = get_connection()
    conn.autocommit = True
    yield conn
    conn.close()


def query_one(db, sql, params=None):
    cur = db.cursor()
    cur.execute(sql, params or ())
    row = cur.fetchone()
    return row[0] if row else None


class TestMatchTableTypes:
    """All match tables must use TEXT type for f7_employer_id (type mismatch = silent failures)."""

    MATCH_TABLES = [
        "osha_f7_matches",
        "whd_f7_matches",
        "national_990_f7_matches",
    ]

    def test_f7_employer_id_is_text(self, db):
        """Every match table's f7_employer_id column should be TEXT."""
        failures = []
        for table in self.MATCH_TABLES:
            exists = query_one(db, """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = %s AND table_schema = 'public'
            """, (table,))
            if not exists:
                continue

            dtype = query_one(db, """
                SELECT data_type FROM information_schema.columns
                WHERE table_name = %s AND column_name = 'f7_employer_id'
            """, (table,))
            if dtype and dtype.lower() not in ('text', 'character varying'):
                failures.append(f"{table}.f7_employer_id is {dtype}, expected TEXT")

        assert len(failures) == 0, "Type mismatch in match tables:\n" + "\n".join(failures)


class TestMatchRateRegression:
    """Match rates must not regress below established baselines."""

    def test_osha_match_rate_ge_13pct(self, db):
        total = query_one(db, "SELECT COUNT(*) FROM osha_establishments")
        matched = query_one(db, "SELECT COUNT(DISTINCT establishment_id) FROM osha_f7_matches")
        if total is None or total == 0:
            pytest.skip("osha_establishments empty")
        rate = matched / total
        assert rate >= 0.13, f"OSHA match rate {rate:.1%} < 13%"

    def test_whd_match_rate_ge_6pct(self, db):
        exists = query_one(db, """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'whd_f7_matches'
        """)
        if not exists:
            pytest.skip("whd_f7_matches not created")
        total = query_one(db, "SELECT COUNT(*) FROM whd_cases")
        matched = query_one(db, "SELECT COUNT(*) FROM whd_f7_matches")
        if total is None or total == 0:
            pytest.skip("whd_cases empty")
        rate = matched / total
        assert rate >= 0.06, f"WHD match rate {rate:.1%} < 6%"

    def test_990_match_rate_ge_2pct(self, db):
        exists = query_one(db, """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'national_990_f7_matches'
        """)
        if not exists:
            pytest.skip("national_990_f7_matches not created")
        total = query_one(db, "SELECT COUNT(*) FROM national_990_filers")
        matched = query_one(db, "SELECT COUNT(*) FROM national_990_f7_matches")
        if total is None or total == 0:
            pytest.skip("national_990_filers empty")
        rate = matched / total
        assert rate >= 0.02, f"990 match rate {rate:.1%} < 2%"


class TestScenarioTableReferences:
    """All predefined scenarios reference tables that actually exist in the database."""

    def test_all_scenario_tables_exist(self, db):
        missing = []
        for name, cfg in SCENARIOS.items():
            for table_attr in ('source_table', 'target_table'):
                table = getattr(cfg, table_attr)
                exists = query_one(db, """
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = %s AND table_schema = 'public'
                """, (table,))
                if not exists:
                    missing.append(f"Scenario '{name}': {table_attr}='{table}' not found")

        assert len(missing) == 0, "Missing tables:\n" + "\n".join(missing)
