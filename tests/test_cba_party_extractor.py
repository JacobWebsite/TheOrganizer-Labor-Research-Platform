"""Unit tests for the CBA party and metadata extractor."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_mod = importlib.import_module("scripts.cba.02_extract_parties")
extract_parties_from_text = _mod.extract_parties_from_text


class TestPartyExtraction:
    def test_between_employer_and_union(self):
        text = (
            "AGREEMENT\n\n"
            "This Agreement is entered into by and between "
            "Realty Advisory Board on Labor Relations, Inc. "
            "and Service Employees International Union, Local 32BJ, AFL-CIO.\n\n"
            "This agreement is effective January 1, 2022."
        )
        meta = extract_parties_from_text(text)
        assert meta.employer_name is not None
        assert "Realty" in meta.employer_name
        assert meta.union_name is not None
        assert "32BJ" in meta.union_name or "Service Employees" in meta.union_name

    def test_union_identified_by_keywords(self):
        text = (
            "Agreement between ABC Manufacturing Company "
            "and United Auto Workers Local 555.\n"
        )
        meta = extract_parties_from_text(text)
        assert meta.union_name is not None
        assert "Auto Workers" in meta.union_name or "555" in meta.union_name

    def test_local_number_extraction(self):
        text = (
            "This agreement between the Company and "
            "SEIU Local 32BJ covers building service workers.\n"
        )
        meta = extract_parties_from_text(text)
        assert meta.local_number is not None
        assert "32" in meta.local_number

    def test_local_no_format(self):
        text = "Agreement with Teamsters Local No. 804."
        meta = extract_parties_from_text(text)
        assert meta.local_number == "804"


class TestDateExtraction:
    def test_effective_date(self):
        text = "This Agreement shall be effective January 1, 2022."
        meta = extract_parties_from_text(text)
        assert meta.effective_date is not None
        assert "January 1, 2022" in meta.effective_date

    def test_expiration_date(self):
        text = "This Agreement shall expire on December 31, 2025."
        meta = extract_parties_from_text(text)
        assert meta.expiration_date is not None
        assert "December 31, 2025" in meta.expiration_date

    def test_period_through(self):
        text = "This Agreement is for the period March 1, 2023 through February 28, 2027."
        meta = extract_parties_from_text(text)
        assert meta.effective_date is not None
        assert "March 1, 2023" in meta.effective_date
        assert meta.expiration_date is not None
        assert "February 28, 2027" in meta.expiration_date

    def test_year_range_in_title(self):
        text = "2022-2026 Apartment Building Agreement\n\nParties and terms follow."
        meta = extract_parties_from_text(text)
        assert meta.effective_date is not None
        assert "2022" in meta.effective_date
        assert meta.expiration_date is not None
        assert "2026" in meta.expiration_date

    def test_numeric_date(self):
        text = "Effective as of 01/15/2024 and ending on 01/14/2028."
        meta = extract_parties_from_text(text)
        assert meta.effective_date is not None
        assert "01/15/2024" in meta.effective_date


class TestGeographyExtraction:
    def test_state_of(self):
        text = "Covering employees in the State of New York."
        meta = extract_parties_from_text(text)
        assert meta.state is not None
        assert "New York" in meta.state

    def test_city_detection(self):
        text = "This agreement covers workers employed in New York, Chicago, and Los Angeles."
        meta = extract_parties_from_text(text)
        assert meta.city is not None

    def test_state_from_comma(self):
        text = "Located in Albany, New York."
        meta = extract_parties_from_text(text)
        assert meta.state is not None


class TestBargainingUnit:
    def test_bargaining_unit_includes(self):
        text = (
            "The bargaining unit shall consist of all full-time and regular part-time "
            "building service employees employed by members of the Association."
        )
        meta = extract_parties_from_text(text)
        assert meta.bargaining_unit is not None
        assert "building service" in meta.bargaining_unit.lower()

    def test_employees_covered(self):
        text = (
            "Employees covered by this agreement include all maintenance workers, "
            "custodians, and porters employed at residential buildings."
        )
        meta = extract_parties_from_text(text)
        assert meta.bargaining_unit is not None


class TestEdgeCases:
    def test_empty_text(self):
        meta = extract_parties_from_text("")
        assert meta.employer_name is None
        assert meta.union_name is None

    def test_no_match(self):
        text = "Random text with no contract language at all."
        meta = extract_parties_from_text(text)
        # Should not crash, fields should be None
        assert meta.effective_date is None

    def test_full_contract_header(self):
        text = (
            "COLLECTIVE BARGAINING AGREEMENT\n\n"
            "2022-2026 Apartment Building Agreement\n\n"
            "between\n\n"
            "Realty Advisory Board on Labor Relations, Inc.\n"
            "(hereinafter referred to as the \"Employer\")\n\n"
            "and\n\n"
            "Service Employees International Union, Local 32BJ\n"
            "(hereinafter referred to as the \"Union\")\n\n"
            "Effective January 1, 2022 through December 31, 2025\n\n"
            "Covering building service employees in the City of New York.\n"
        )
        meta = extract_parties_from_text(text)
        assert meta.employer_name is not None
        assert meta.union_name is not None
        assert meta.effective_date is not None
        assert meta.state is not None or meta.city is not None
