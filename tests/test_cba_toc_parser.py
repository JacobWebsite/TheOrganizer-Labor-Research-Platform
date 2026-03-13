"""Tests for CBA TOC parser (05_parse_toc.py)."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.cba.models import TOCEntry

_toc_mod = importlib.import_module("scripts.cba.05_parse_toc")
ARTICLE_TOC_RE = _toc_mod.ARTICLE_TOC_RE
CONTINUATION_RE = _toc_mod.CONTINUATION_RE
DOTTED_LEADER_RE = _toc_mod.DOTTED_LEADER_RE
NON_ARTICLE_TOC_RE = _toc_mod.NON_ARTICLE_TOC_RE
SUB_SECTION_TOC_RE = _toc_mod.SUB_SECTION_TOC_RE
_clean_toc_title = _toc_mod._clean_toc_title
_merge_multiline_titles = _toc_mod._merge_multiline_titles
_normalize_num = _toc_mod._normalize_num
_parse_toc_block = _toc_mod._parse_toc_block
parse_toc = _toc_mod.parse_toc
toc_entries_to_json = _toc_mod.toc_entries_to_json


# ---- 32BJ-style TOC text for integration tests ----
SAMPLE_TOC_32BJ = """
                         TABLE OF CONTENTS

I.   Union Recognition and Union Security .................1
II.  Wages ...............................................10
III. Hours and Overtime ..................................15
IV.  Holidays ............................................22
V.   Vacations ...........................................25
VI.  Sick Leave ..........................................30
VII. Health Benefits .....................................35
VIII.Pension .............................................42
IX.  Supplemental Retirement and Savings ................50
X.   Legal Services ......................................55
XI.  Training and Upgrading ..............................58
XII. Discharge and Discipline ............................62
XIII.Grievance and Arbitration ...........................65
XIV. No Strike - No Lockout .............................70
XV.  Management Rights ...................................72
XVI. Health and Safety ...................................74
XVII.Jury Duty ...........................................75
XVIII.Bereavement Leave ..................................76
XIX. General Clauses .....................................77
   1. Uniforms ..........................................77
   2. Tools and Equipment ...............................78
   3. Locker Rooms ......................................79
   4. Bulletin Boards ...................................80
   5. Voting Time .......................................81
   6. Military Leave ....................................82
   7. Immigration .......................................83
   8. Separability ......................................84
   9. Building Sales ....................................85
   10. Successors and Assigns ...........................86
   11. Duration .........................................87
XX.  Signatory Buildings / Multi-Employer Bargaining .....88

Side Letters ............................................126
Minimum Wage Rates ......................................139

"""

# Same text with contract body appended
SAMPLE_FULL_TEXT = SAMPLE_TOC_32BJ + """

ARTICLE I
UNION RECOGNITION AND UNION SECURITY

Section 1. The Employer recognizes the Union as the sole and exclusive
collective bargaining representative for all employees in the bargaining unit...

ARTICLE II
WAGES

Section 1. Effective January 1, 2023, the minimum wage rate shall be $22.50
per hour for all classifications...
"""


class TestRegexPatterns:
    """Test individual regex patterns match TOC line formats."""

    def test_article_toc_re_roman(self):
        m = ARTICLE_TOC_RE.match("I.   Union Recognition and Union Security .................1")
        assert m is not None
        assert m.group(1) == "I"
        assert "Union Recognition" in m.group(2)
        assert m.group(3) == "1"

    def test_article_toc_re_roman_multi_char(self):
        m = ARTICLE_TOC_RE.match("XIX. General Clauses .....................................77")
        assert m is not None
        assert m.group(1) == "XIX"
        assert m.group(3) == "77"

    def test_article_toc_re_arabic(self):
        m = ARTICLE_TOC_RE.match("12.  Wages and Benefits ..................................45")
        assert m is not None

    def test_sub_section_toc_re(self):
        m = SUB_SECTION_TOC_RE.match("   5. Voting Time .......................................81")
        assert m is not None
        assert m.group(1) == "5"
        assert "Voting Time" in m.group(2)
        assert m.group(3) == "81"

    def test_non_article_toc_re(self):
        m = NON_ARTICLE_TOC_RE.match("Side Letters ............................................126")
        assert m is not None
        assert "Side Letters" in m.group(1)
        assert m.group(2) == "126"

    def test_dotted_leader_basic(self):
        m = DOTTED_LEADER_RE.match("Something here ................42")
        assert m is not None
        assert m.group(2) == "42"

    def test_continuation_re(self):
        assert CONTINUATION_RE.search("XIX. General Clauses (cont'd)")
        assert CONTINUATION_RE.search("XIX. General Clauses (continued)")
        assert not CONTINUATION_RE.search("XIX. General Clauses")


class TestNormalizeNum:
    def test_roman_to_arabic(self):
        assert _normalize_num("I") == "1"
        assert _normalize_num("XIX") == "19"
        assert _normalize_num("XX") == "20"

    def test_arabic_passthrough(self):
        assert _normalize_num("12") == "12"
        assert _normalize_num("5") == "5"


class TestCleanTitle:
    def test_strips_trailing_dots(self):
        assert _clean_toc_title("Wages and Benefits...") == "Wages and Benefits"

    def test_strips_trailing_punctuation(self):
        assert _clean_toc_title("Union Security -") == "Union Security"
        assert _clean_toc_title("Wages:") == "Wages"

    def test_collapses_whitespace(self):
        assert _clean_toc_title("Health   and   Safety") == "Health and Safety"


class TestMergeMultilineTitles:
    def test_merges_same_page_entries(self):
        entries = [
            TOCEntry(number="20", title="Signatory Buildings / Multi-Employer", page_number=88, level=1),
            TOCEntry(number="Bargaining", title="Bargaining", page_number=88, level=1),
        ]
        merged = _merge_multiline_titles(entries)
        assert len(merged) == 1
        assert "Signatory" in merged[0].title
        assert "Bargaining" in merged[0].title

    def test_no_merge_different_pages(self):
        entries = [
            TOCEntry(number="19", title="General Clauses", page_number=77, level=1),
            TOCEntry(number="20", title="Bargaining", page_number=88, level=1),
        ]
        merged = _merge_multiline_titles(entries)
        assert len(merged) == 2


class TestParseTocBlock:
    """Test _parse_toc_block on structured TOC text."""

    def test_parses_articles(self):
        entries = _parse_toc_block(SAMPLE_TOC_32BJ, SAMPLE_TOC_32BJ.index("I."))
        articles = [e for e in entries if e.level == 1 and e.number != e.title]
        assert len(articles) >= 19  # I through XX

    def test_parses_sub_sections(self):
        entries = _parse_toc_block(SAMPLE_TOC_32BJ, SAMPLE_TOC_32BJ.index("I."))
        subs = [e for e in entries if e.level == 2]
        assert len(subs) >= 10  # Article XIX sub-sections

    def test_parses_non_article_entries(self):
        entries = _parse_toc_block(SAMPLE_TOC_32BJ, SAMPLE_TOC_32BJ.index("I."))
        titles = [e.title for e in entries]
        assert any("Side Letters" in t for t in titles)
        assert any("Minimum Wage" in t for t in titles)

    def test_sub_section_parent_numbers(self):
        entries = _parse_toc_block(SAMPLE_TOC_32BJ, SAMPLE_TOC_32BJ.index("I."))
        subs = [e for e in entries if e.level == 2]
        # All sub-sections should have parent_number = "19" (Article XIX)
        for s in subs:
            assert s.parent_number == "19", f"{s.number} has parent {s.parent_number}"

    def test_page_numbers_correct(self):
        entries = _parse_toc_block(SAMPLE_TOC_32BJ, SAMPLE_TOC_32BJ.index("I."))
        entry_map = {e.number: e for e in entries}
        assert entry_map["1"].page_number == 1     # Article I
        assert entry_map["2"].page_number == 10    # Article II (Wages)
        assert entry_map["19"].page_number == 77   # Article XIX


class TestParseTocIntegration:
    """Test the full parse_toc() function."""

    def test_finds_toc_header(self):
        entries = parse_toc(SAMPLE_TOC_32BJ)
        assert len(entries) > 0

    def test_entry_count(self):
        entries = parse_toc(SAMPLE_TOC_32BJ)
        # 20 articles + 11 sub-sections + 2 non-article = ~33
        assert len(entries) >= 30

    def test_with_full_text(self):
        entries = parse_toc(SAMPLE_FULL_TEXT)
        assert len(entries) >= 30

    def test_returns_empty_for_no_toc(self):
        entries = parse_toc("This is just plain text with no table of contents.")
        assert entries == []


class TestTocEntriesToJson:
    def test_roundtrip(self):
        entries = [
            TOCEntry(number="1", title="Wages", page_number=10, level=1),
            TOCEntry(number="1.5", title="Overtime", page_number=15, level=2, parent_number="1"),
        ]
        data = toc_entries_to_json(entries)
        assert len(data) == 2
        assert data[0]["number"] == "1"
        assert data[0]["title"] == "Wages"
        assert data[1]["parent_number"] == "1"


class TestEdgeCases:
    def test_unicode_dots(self):
        """Test with middle dot (U+00B7) leaders."""
        text = """TABLE OF CONTENTS
I.   Wages \u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7 10
II.  Hours \u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7\u00b7 20
"""
        entries = parse_toc(text)
        assert len(entries) >= 2

    def test_ellipsis_char(self):
        """Test with actual ellipsis character (U+2026)."""
        text = """TABLE OF CONTENTS
I.   Wages \u2026\u2026\u2026\u2026\u2026 10
II.  Hours \u2026\u2026\u2026\u2026\u2026 20
"""
        entries = parse_toc(text)
        assert len(entries) >= 2

    def test_article_prefix(self):
        """Test TOC lines with explicit ARTICLE prefix."""
        text = """TABLE OF CONTENTS
ARTICLE I - Union Recognition .................1
ARTICLE II - Wages ............................10
ARTICLE III - Hours ...........................15
"""
        entries = parse_toc(text)
        assert len(entries) == 3
        assert entries[0].number == "1"
        assert entries[0].title == "Union Recognition"
