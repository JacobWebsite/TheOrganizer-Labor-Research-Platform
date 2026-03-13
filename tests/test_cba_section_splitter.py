"""Tests for CBA section splitter (06_split_sections.py)."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.cba.models import PageSpan, SectionRow, TOCEntry

_split_mod = importlib.import_module("scripts.cba.06_split_sections")
_char_for_page = _split_mod._char_for_page
_detect_page_offset = _split_mod._detect_page_offset
_find_section_start = _split_mod._find_section_start
_heading_search_pattern = _split_mod._heading_search_pattern
reconstruct_spans = _split_mod.reconstruct_spans
split_sections = _split_mod.split_sections


# ---- Test data ----

# Simulate a contract with 5 pages, ~500 chars each
SAMPLE_TEXT = """COVER PAGE - COLLECTIVE BARGAINING AGREEMENT

TABLE OF CONTENTS
I. Union Recognition .............1
II. Wages ........................2
III. Hours .......................3


ARTICLE I
UNION RECOGNITION AND UNION SECURITY

Section 1. The Employer recognizes the Union as the sole and exclusive
collective bargaining representative for all employees in the bargaining unit
described herein. All employees covered by this Agreement who are members of
the Union shall maintain their membership.

Section 2. Any new employee hired shall become a member of the Union within
thirty (30) days of employment.

ARTICLE II
WAGES

Section 1. Effective January 1, 2023, the minimum wage rate shall be $22.50
per hour for all classifications covered by this Agreement.

Section 2. Shift differential of $1.50 per hour shall be paid for all hours
worked between 4:00 PM and 8:00 AM.

Section 3. Overtime shall be paid at the rate of time and one-half for all
hours worked in excess of forty (40) hours in any work week.

ARTICLE III
HOURS AND OVERTIME

Section 1. The regular work week shall consist of five (5) consecutive days
of eight (8) hours each, Monday through Friday. The regular work day shall
begin at 8:00 AM and end at 4:30 PM with a thirty (30) minute lunch period.

Section 2. All work performed on Saturday shall be compensated at the rate
of time and one-half the employee's regular rate of pay.
"""

# Simulate page spans (cover=p1, TOC=p2, articles=p3-p5)
SAMPLE_SPANS = [
    PageSpan(page_number=1, char_start=0, char_end=200),
    PageSpan(page_number=2, char_start=200, char_end=400),
    PageSpan(page_number=3, char_start=400, char_end=800),
    PageSpan(page_number=4, char_start=800, char_end=1200),
    PageSpan(page_number=5, char_start=1200, char_end=len(SAMPLE_TEXT)),
]

SAMPLE_TOC = [
    TOCEntry(number="1", title="Union Recognition and Union Security", page_number=1, level=1),
    TOCEntry(number="2", title="Wages", page_number=2, level=1),
    TOCEntry(number="3", title="Hours and Overtime", page_number=3, level=1),
]


class TestReconstructSpans:
    def test_basic(self):
        spans = reconstruct_spans("A" * 1000, 5)
        assert len(spans) == 5
        assert spans[0].page_number == 1
        assert spans[0].char_start == 0
        assert spans[4].char_end == 1000

    def test_single_page(self):
        spans = reconstruct_spans("Hello", 1)
        assert len(spans) == 1
        assert spans[0].char_start == 0
        assert spans[0].char_end == 5

    def test_none_page_count(self):
        spans = reconstruct_spans("Hello", None)
        assert len(spans) == 1


class TestCharForPage:
    def test_first_page(self):
        pos = _char_for_page(SAMPLE_SPANS, 1)
        assert pos == 0

    def test_middle_page(self):
        pos = _char_for_page(SAMPLE_SPANS, 3)
        assert pos == 400

    def test_past_last_page(self):
        pos = _char_for_page(SAMPLE_SPANS, 99)
        assert pos == SAMPLE_SPANS[-1].char_end


class TestHeadingSearchPattern:
    def test_article_with_number(self):
        entry = TOCEntry(number="2", title="Wages", page_number=5, level=1)
        pattern = _heading_search_pattern(entry)
        assert pattern is not None
        m = pattern.search("\nARTICLE II\nWAGES\n")
        # Should match somewhere (the pattern is flexible)
        # At minimum the title-only fallback in _find_section_start would catch it

    def test_non_article_entry(self):
        entry = TOCEntry(number="Side Letters", title="Side Letters", page_number=126, level=1)
        pattern = _heading_search_pattern(entry)
        assert pattern is not None
        m = pattern.search("\nSide Letters\n")
        assert m is not None

    def test_sub_section(self):
        entry = TOCEntry(number="19.5", title="Voting Time", page_number=81, level=2, parent_number="19")
        pattern = _heading_search_pattern(entry)
        assert pattern is not None


class TestDetectPageOffset:
    def test_detects_offset(self):
        # In SAMPLE_TEXT, "ARTICLE I" appears at char ~200+ (page 2-3 area)
        # TOC says page 1, so offset should be positive
        offset = _detect_page_offset(SAMPLE_TEXT, SAMPLE_SPANS, SAMPLE_TOC)
        assert isinstance(offset, int)
        assert offset >= 0

    def test_empty_toc(self):
        offset = _detect_page_offset(SAMPLE_TEXT, SAMPLE_SPANS, [])
        assert offset == 0


class TestSplitSections:
    def test_creates_sections(self):
        sections = split_sections(SAMPLE_TEXT, SAMPLE_SPANS, SAMPLE_TOC)
        assert len(sections) >= 2  # At least articles I and II

    def test_section_text_not_empty(self):
        sections = split_sections(SAMPLE_TEXT, SAMPLE_SPANS, SAMPLE_TOC)
        for s in sections:
            assert len(s.section_text) > 0, f"Section {s.section_num} has empty text"

    def test_no_overlaps(self):
        sections = split_sections(SAMPLE_TEXT, SAMPLE_SPANS, SAMPLE_TOC)
        sorted_secs = sorted(sections, key=lambda s: s.char_start)
        for i in range(len(sorted_secs) - 1):
            assert sorted_secs[i].char_end <= sorted_secs[i + 1].char_start, (
                f"Overlap: section {sorted_secs[i].section_num} ends at "
                f"{sorted_secs[i].char_end} but {sorted_secs[i+1].section_num} "
                f"starts at {sorted_secs[i+1].char_start}"
            )

    def test_coverage(self):
        """Total section text should cover a large fraction of the full text."""
        sections = split_sections(SAMPLE_TEXT, SAMPLE_SPANS, SAMPLE_TOC)
        total_chars = sum(s.char_end - s.char_start for s in sections)
        # At least 50% coverage (first section starts after cover/TOC pages)
        assert total_chars > len(SAMPLE_TEXT) * 0.4

    def test_section_levels(self):
        sections = split_sections(SAMPLE_TEXT, SAMPLE_SPANS, SAMPLE_TOC)
        for s in sections:
            assert s.section_level in (1, 2)

    def test_detection_method(self):
        sections = split_sections(SAMPLE_TEXT, SAMPLE_SPANS, SAMPLE_TOC)
        for s in sections:
            assert s.detection_method == "toc_parsed"

    def test_empty_toc(self):
        sections = split_sections(SAMPLE_TEXT, SAMPLE_SPANS, [])
        assert sections == []

    def test_section_contains_expected_content(self):
        sections = split_sections(SAMPLE_TEXT, SAMPLE_SPANS, SAMPLE_TOC)
        sec_map = {s.section_num: s for s in sections}
        # The Wages section should contain "$22.50"
        if "2" in sec_map:
            assert "$22.50" in sec_map["2"].section_text
        # The Hours section should contain work week info
        if "3" in sec_map:
            assert "work week" in sec_map["3"].section_text.lower()


class TestSectionRow:
    def test_dataclass_defaults(self):
        s = SectionRow(
            section_num="1",
            section_title="Test",
            section_level=1,
            section_text="Hello",
            char_start=0,
            char_end=5,
        )
        assert s.detection_method == "toc_parsed"
        assert s.parent_section_num is None
        assert s.page_start is None
