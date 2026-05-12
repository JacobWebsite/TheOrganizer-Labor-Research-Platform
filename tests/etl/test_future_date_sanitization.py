"""Regression tests for FEC + SEC XBRL future-date sanitization.

These tests cover the date-validator helpers in the loaders and the
CHECK constraints on the destination tables. The point is to keep
the 2026-05-12 cleanup from regressing -- if anything starts letting
3312-01-01 through again, these tests fail loudly.

Two halves:

1. Pure helper tests (no DB) -- exercise the loader normalizers
   (``load_fec._norm_date`` / ``load_fec._norm_year`` /
   ``load_sec_xbrl.extract_annual_facts``) against canonical garbage
   inputs. These run on every CI invocation.

2. DB invariants (requires a working ``db_config.get_connection()``) --
   assert that no garbage rows exist and that the CHECK constraints
   are wired up so any future bad insert is rejected before it lands.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.etl import load_fec, load_sec_xbrl  # noqa: E402


# ---------------------------------------------------------------------------
# Section 1 -- pure helper sanitization tests (no DB)
# ---------------------------------------------------------------------------


class TestFecNormDate:
    """``load_fec._norm_date`` rejects garbage and accepts real dates."""

    def test_accepts_recent_real_date(self):
        # FEC dates are MMDDYYYY string.
        assert load_fec._norm_date("01012023") == date(2023, 1, 1)

    def test_accepts_boundary_today_plus_one_year(self):
        # Any year up to today + 1 should pass.
        today_year = date.today().year
        result = load_fec._norm_date(f"0101{today_year + 1}")
        assert result is not None and result.year == today_year + 1

    def test_rejects_year_3312(self):
        # The historical sentinel that gave the bug its name.
        assert load_fec._norm_date("01013312") is None

    def test_rejects_pre_1980(self):
        assert load_fec._norm_date("01011979") is None

    def test_rejects_far_future(self):
        # Years more than 1 ahead of today are typos.
        today_year = date.today().year
        assert load_fec._norm_date(f"0101{today_year + 5}") is None

    def test_rejects_malformed_input(self):
        # All of these should silently return None (not raise).
        for bad in (None, "", "1", "abc", "01012023bad", "12345"):
            assert load_fec._norm_date(bad) is None

    def test_does_not_raise_on_valid_dates(self):
        """Regression for the NameError bug fixed 2026-05-12.

        Before the fix, ``_norm_date`` raised
        ``NameError: name 'date' is not defined`` for every parseable
        date because the ``date`` symbol was missing from the import line.
        This test asserts the function returns cleanly without raising.
        """
        # Just exercise a handful of valid inputs; if any raises, fail.
        for v in ("01012023", "12312024", "05122026"):
            load_fec._norm_date(v)  # must not raise


class TestFecNormYear:
    """``load_fec._norm_year`` rejects keystroke typos like 2929."""

    def test_accepts_recent_year(self):
        assert load_fec._norm_year("2024") == 2024

    def test_rejects_pre_1980(self):
        assert load_fec._norm_year("1979") is None

    def test_rejects_year_2929(self):
        # Real garbage that survived in fec_candidates before cleanup.
        assert load_fec._norm_year("2929") is None

    def test_rejects_year_2106(self):
        assert load_fec._norm_year("2106") is None

    def test_accepts_decade_ahead(self):
        # Allow up to today + 10 since candidates may declare a decade out.
        today_year = date.today().year
        assert load_fec._norm_year(str(today_year + 5)) == today_year + 5

    def test_rejects_two_decades_ahead(self):
        today_year = date.today().year
        assert load_fec._norm_year(str(today_year + 20)) is None

    def test_handles_garbage_input(self):
        for bad in (None, "", "abc", "  "):
            assert load_fec._norm_year(bad) is None


class TestSecXbrlExtractRejectsFutureDates:
    """``load_sec_xbrl.extract_annual_facts`` filters bad fiscal_year_end."""

    @staticmethod
    def _company_data(end_date: str, filed: str = "2024-03-15", val: float = 1e9):
        """Build a minimal SEC companyfacts payload with one Revenue tag entry."""
        return {
            "cik": 9999999,
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "form": "10-K",
                                    "end": end_date,
                                    "filed": filed,
                                    "fp": "FY",
                                    "val": val,
                                }
                            ]
                        }
                    }
                }
            },
        }

    def test_accepts_real_recent_fy_end(self):
        rejects: dict = {}
        rows = load_sec_xbrl.extract_annual_facts(
            self._company_data("2023-12-31", filed="2024-02-22"),
            date_reject_counter=rejects,
        )
        assert len(rows) == 1
        assert rows[0]["fiscal_year_end"] == "2023-12-31"
        assert rejects == {}

    def test_rejects_year_2201(self):
        rejects: dict = {}
        rows = load_sec_xbrl.extract_annual_facts(
            self._company_data("2201-12-31"),
            date_reject_counter=rejects,
        )
        assert rows == []
        assert rejects.get("2201-12-31") == 1

    def test_rejects_pre_1990(self):
        rejects: dict = {}
        rows = load_sec_xbrl.extract_annual_facts(
            self._company_data("1989-12-31"),
            date_reject_counter=rejects,
        )
        assert rows == []
        assert rejects.get("1989-12-31") == 1

    def test_rejects_filed_before_fy_end(self):
        """A 10-K cannot be filed before its fiscal period closes.

        This catches the SEC-source bug class where a projection tag got
        cross-attributed to a 10-K filing, surfacing 25 rows in the
        production table before the 2026-05-12 cleanup.
        """
        rejects: dict = {}
        rows = load_sec_xbrl.extract_annual_facts(
            self._company_data("2025-12-31", filed="2024-02-22"),
            date_reject_counter=rejects,
        )
        assert rows == []
        # Should be tagged with the "_filed_before" marker.
        assert any(k.endswith("_filed_before") for k in rejects)


# ---------------------------------------------------------------------------
# Section 2 -- DB invariant assertions (requires live DB)
# ---------------------------------------------------------------------------


def _db_or_skip():
    """Return a live DB cursor or skip the DB tests."""
    try:
        from db_config import get_connection
    except Exception as e:
        pytest.skip(f"db_config unavailable: {e}")
    try:
        conn = get_connection()
    except Exception as e:
        pytest.skip(f"DB not reachable: {e}")
    return conn


def test_db_fec_indiv_no_future_garbage():
    conn = _db_or_skip()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM fec_individual_contributions "
                "WHERE transaction_dt > CURRENT_DATE + INTERVAL '1 year'"
            )
            (cnt,) = cur.fetchone()
            assert cnt == 0, (
                f"fec_individual_contributions has {cnt} rows with transaction_dt "
                "more than 1 year in the future; loader sanitization regressed"
            )
    finally:
        conn.close()


def test_db_fec_pas2_no_future_garbage():
    conn = _db_or_skip()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM fec_committee_contributions "
                "WHERE transaction_dt > CURRENT_DATE + INTERVAL '1 year'"
            )
            (cnt,) = cur.fetchone()
            assert cnt == 0
    finally:
        conn.close()


def test_db_fec_candidates_no_garbage_election_year():
    conn = _db_or_skip()
    try:
        with conn.cursor() as cur:
            today_plus_10 = date.today().year + 10
            cur.execute(
                "SELECT COUNT(*) FROM fec_candidates "
                "WHERE cand_election_yr > %s",
                (today_plus_10,),
            )
            (cnt,) = cur.fetchone()
            assert cnt == 0
    finally:
        conn.close()


def test_db_sec_xbrl_no_future_fy_end():
    conn = _db_or_skip()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM sec_xbrl_financials WHERE fiscal_year_end > '2032-12-31'"
            )
            (cnt,) = cur.fetchone()
            assert cnt == 0
    finally:
        conn.close()


def test_db_sec_xbrl_no_filed_before_fy_end():
    """A 10-K cannot be filed before fiscal_year_end."""
    conn = _db_or_skip()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM sec_xbrl_financials "
                "WHERE filed_date IS NOT NULL AND fiscal_year_end > filed_date"
            )
            (cnt,) = cur.fetchone()
            assert cnt == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Section 3 -- CHECK constraint presence (asserts the wall is up)
# ---------------------------------------------------------------------------


EXPECTED_CONSTRAINTS = {
    "chk_fec_indiv_transaction_dt_sane",
    "chk_fec_pas2_transaction_dt_sane",
    "chk_fec_candidates_election_yr_sane",
    "chk_sec_xbrl_fy_end_sane",
    "chk_sec_xbrl_filed_after_fy_end",
}


def test_db_check_constraints_present():
    conn = _db_or_skip()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT conname FROM pg_constraint WHERE conname = ANY(%s)",
                (list(EXPECTED_CONSTRAINTS),),
            )
            found = {r[0] for r in cur.fetchall()}
            missing = EXPECTED_CONSTRAINTS - found
            assert not missing, (
                f"Missing CHECK constraints in DB: {sorted(missing)}. "
                "Re-run scripts/etl/load_fec.py and scripts/etl/load_sec_xbrl.py "
                "to recreate, or apply the 2026-05-12 cleanup migration."
            )
    finally:
        conn.close()


def test_db_check_constraint_rejects_garbage_indiv_date():
    """Bottom-line invariant: trying to insert 3312-01-01 must fail."""
    import psycopg2.errors

    conn = _db_or_skip()
    try:
        with conn.cursor() as cur:
            # Use a sub_id that cannot collide with real data.
            cur.execute("SAVEPOINT prebadinsert")
            try:
                cur.execute(
                    "INSERT INTO fec_individual_contributions "
                    "(sub_id, transaction_dt) VALUES (-1, '3312-01-01')"
                )
            except psycopg2.errors.CheckViolation:
                ok = True
            except psycopg2.errors.NotNullViolation:
                # Other NOT NULL columns may also reject; that's still a pass for our purpose.
                # But we want the CHECK to be the one that fires; retry with a softer payload.
                cur.execute("ROLLBACK TO SAVEPOINT prebadinsert")
                pytest.skip(
                    "fec_individual_contributions has additional NOT NULL columns; "
                    "CHECK presence is asserted by test_db_check_constraints_present"
                )
                return
            else:
                ok = False
                cur.execute("ROLLBACK TO SAVEPOINT prebadinsert")
            assert ok, "CHECK chk_fec_indiv_transaction_dt_sane did not block 3312-01-01"
            cur.execute("ROLLBACK TO SAVEPOINT prebadinsert")
    finally:
        conn.rollback()
        conn.close()
