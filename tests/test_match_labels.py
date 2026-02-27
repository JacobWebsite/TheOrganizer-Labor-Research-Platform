"""Tests for match label utilities and match_summary in API responses."""
import pytest

from api.match_labels import build_citation, build_master_citation, SOURCE_LABELS


class TestBuildCitation:
    def test_ein_exact(self):
        result = build_citation("osha", "EIN_EXACT")
        assert result == "OSHA Establishment Records matched by EIN (exact match)"

    def test_name_city_state(self):
        result = build_citation("whd", "NAME_CITY_STATE")
        assert result == "DOL Wage & Hour Division matched by name + city + state"

    def test_fuzzy_with_score(self):
        result = build_citation("nlrb", "FUZZY_SPLINK_ADAPTIVE", 0.872)
        assert "fuzzy name matching" in result
        assert "0.87 similarity" in result
        assert result.startswith("NLRB Case Records")

    def test_trigram_with_score(self):
        result = build_citation("bmf", "TRIGRAM", 0.91)
        assert "trigram similarity" in result
        assert "0.91 similarity" in result

    def test_unknown_source(self):
        result = build_citation("xyz_new", "EIN_EXACT")
        assert "XYZ_NEW" in result

    def test_unknown_method(self):
        result = build_citation("osha", "SOME_NEW_METHOD")
        assert "SOME_NEW_METHOD" in result

    def test_none_source(self):
        result = build_citation(None, "EIN_EXACT")
        assert "Unknown" in result

    def test_fuzzy_without_score(self):
        result = build_citation("osha", "FUZZY_SPLINK_ADAPTIVE")
        assert "similarity" not in result
        assert "fuzzy name matching" in result


class TestBuildMasterCitation:
    def test_exact_match(self):
        result = build_master_citation("osha", 1.0)
        assert result == "OSHA Establishment Records (exact match)"

    def test_partial_confidence(self):
        result = build_master_citation("nlrb", 0.85)
        assert "NLRB Case Records" in result
        assert "85%" in result

    def test_no_confidence(self):
        result = build_master_citation("sec")
        assert result == "SEC EDGAR Filings"

    def test_unknown_source(self):
        result = build_master_citation("newdb", 0.9)
        assert "newdb" in result.lower()


class TestMatchSummaryEndpoint:
    """Integration tests for match_summary in /api/employers/{id}/matches"""

    def test_match_summary_key_present(self, client):
        from db_config import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT employer_id FROM f7_employers_deduped LIMIT 1")
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            pytest.skip("No employers in database")

        r = client.get(f"/api/employers/{row[0]}/matches")
        assert r.status_code == 200
        data = r.json()
        assert "match_summary" in data
        assert isinstance(data["match_summary"], list)

    def test_match_summary_fields(self, client):
        from db_config import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # Find an employer that has active matches
                cur.execute("""
                    SELECT DISTINCT target_id
                    FROM unified_match_log
                    WHERE target_system = 'f7' AND status = 'active'
                    LIMIT 1
                """)
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            pytest.skip("No matched employers")

        r = client.get(f"/api/employers/{row[0]}/matches")
        assert r.status_code == 200
        data = r.json()

        if not data["match_summary"]:
            pytest.skip("No match summary rows")

        entry = data["match_summary"][0]
        assert "source_system" in entry
        assert "source_label" in entry
        assert "match_count" in entry
        assert "citation" in entry
        assert entry["match_count"] >= 1
        assert len(entry["citation"]) > 0

    def test_backward_compat_matches_key(self, client):
        """Existing 'matches' key must still be present."""
        from db_config import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT employer_id FROM f7_employers_deduped LIMIT 1")
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            pytest.skip("No employers")

        r = client.get(f"/api/employers/{row[0]}/matches")
        assert r.status_code == 200
        data = r.json()
        assert "matches" in data
        assert "employer_id" in data


class TestMasterMatchSummary:
    """Integration tests for match_summary in /api/master/{id}"""

    def test_master_detail_has_match_summary(self, client):
        from db_config import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # Try both possible PK column names
                try:
                    cur.execute("SELECT master_id FROM master_employers LIMIT 1")
                except Exception:
                    cur.execute("SELECT id FROM master_employers LIMIT 1")
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            pytest.skip("No master employers")

        master_id = row[0]
        r = client.get(f"/api/master/{master_id}")
        assert r.status_code == 200
        data = r.json()
        assert "match_summary" in data
        assert isinstance(data["match_summary"], list)

        # Each entry should have citation
        for entry in data["match_summary"]:
            assert "source_system" in entry
            assert "citation" in entry
            assert "match_count" in entry
