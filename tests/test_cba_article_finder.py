"""Unit tests for the CBA article/section finder."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.cba.models import PageSpan

_mod = importlib.import_module("scripts.cba.03_find_articles")
find_articles = _mod.find_articles
chunks_to_json = _mod.chunks_to_json


def test_article_with_number_and_title():
    text = (
        "\n\nARTICLE 1 - RECOGNITION\n\n"
        "The employer recognizes the union as the exclusive bargaining representative.\n\n"
        "ARTICLE 2 - MANAGEMENT RIGHTS\n\n"
        "The employer retains all management rights not limited by this agreement.\n\n"
        "ARTICLE 3 - GRIEVANCE PROCEDURE\n\n"
        "A grievance is defined as any dispute under this agreement.\n"
    )
    chunks = find_articles(text)
    assert len(chunks) == 3
    assert chunks[0].title == "RECOGNITION"
    assert chunks[1].title == "MANAGEMENT RIGHTS"
    assert chunks[2].title == "GRIEVANCE PROCEDURE"


def test_roman_numeral_articles():
    text = (
        "\n\nARTICLE I - RECOGNITION\n\n"
        "Recognition language here.\n\n"
        "ARTICLE II - UNION SECURITY\n\n"
        "Security language here.\n\n"
        "ARTICLE III - WAGES\n\n"
        "Wage language here.\n"
    )
    chunks = find_articles(text)
    assert len(chunks) == 3
    assert chunks[0].number == "1"
    assert chunks[1].number == "2"
    assert chunks[2].number == "3"


def test_mixed_case_articles():
    text = (
        "\n\nArticle 1. Recognition\n\n"
        "The employer recognizes the union.\n\n"
        "Article 2. Management Rights\n\n"
        "Management retains all rights.\n"
    )
    chunks = find_articles(text)
    assert len(chunks) == 2
    assert chunks[0].title == "Recognition"


def test_section_headings():
    text = (
        "\n\nARTICLE 5 - WAGES\n\n"
        "Wages are governed by this article.\n\n"
        "SECTION 5.1 - Base Pay\n\n"
        "Base pay shall be $20 per hour.\n\n"
        "SECTION 5.2 - Overtime\n\n"
        "Overtime at time and one half.\n"
    )
    chunks = find_articles(text)
    assert len(chunks) == 3
    # Section should be level 2
    assert chunks[0].level == 1
    assert chunks[1].level == 2
    assert chunks[2].level == 2


def test_article_number_only_then_title_on_next_line():
    text = (
        "\n\nARTICLE 7\n"
        "GRIEVANCE AND ARBITRATION\n\n"
        "Any dispute shall be resolved through the grievance procedure.\n\n"
        "ARTICLE 8\n"
        "SENIORITY\n\n"
        "Seniority is based on continuous service.\n"
    )
    chunks = find_articles(text)
    assert len(chunks) == 2
    assert "GRIEVANCE" in chunks[0].title
    assert "SENIORITY" in chunks[1].title


def test_allcaps_headings():
    text = (
        "\n\nRECOGNITION\n\n"
        "The employer recognizes the union.\n\n"
        "MANAGEMENT RIGHTS\n\n"
        "Management retains all rights.\n\n"
        "WAGES AND COMPENSATION\n\n"
        "Wages shall be as specified.\n"
    )
    chunks = find_articles(text)
    assert len(chunks) == 3
    assert chunks[0].title == "RECOGNITION"


def test_running_header_excluded():
    """Lines repeated 3+ times should be excluded as running headers."""
    header = "COLLECTIVE BARGAINING AGREEMENT 2024-2027"
    text = (
        f"\n\n{header}\n\n"
        "ARTICLE 1 - RECOGNITION\n\n"
        f"Recognition language here.\n\n{header}\n\n"
        "ARTICLE 2 - WAGES\n\n"
        f"Wage language here.\n\n{header}\n\n"
        "More text.\n"
    )
    chunks = find_articles(text)
    # Should have 2 articles, not extra entries for the running header
    titles = [c.title for c in chunks]
    assert "RECOGNITION" in titles
    assert "WAGES" in titles
    assert header not in titles


def test_empty_text():
    chunks = find_articles("")
    assert chunks == []


def test_no_headings():
    text = "This is just a paragraph of text without any article headings at all."
    chunks = find_articles(text)
    assert chunks == []


def test_char_offsets_are_correct():
    text = (
        "\n\nARTICLE 1 - FIRST\n\n"
        "Content of article one.\n\n"
        "ARTICLE 2 - SECOND\n\n"
        "Content of article two.\n"
    )
    chunks = find_articles(text)
    assert len(chunks) == 2
    # First chunk's text should start with "ARTICLE 1"
    assert chunks[0].text.strip().startswith("ARTICLE 1")
    # Second chunk's text should start with "ARTICLE 2"
    assert chunks[1].text.strip().startswith("ARTICLE 2")
    # char_end of first should equal char_start of second
    assert chunks[0].char_end == chunks[1].char_start


def test_page_mapping_with_spans():
    text = "A" * 1000 + "\n\nARTICLE 1 - TEST\n\n" + "B" * 500
    spans = [
        PageSpan(page_number=1, char_start=0, char_end=500),
        PageSpan(page_number=2, char_start=500, char_end=1000),
        PageSpan(page_number=3, char_start=1000, char_end=len(text)),
    ]
    chunks = find_articles(text, spans)
    assert len(chunks) >= 1
    assert chunks[0].page_start == 3


def test_chunks_to_json():
    text = (
        "\n\nARTICLE 1 - TEST\n\n"
        "Test content.\n"
    )
    chunks = find_articles(text)
    json_data = chunks_to_json(chunks)
    assert isinstance(json_data, list)
    assert len(json_data) == 1
    assert json_data[0]["number"] == "1"
    assert json_data[0]["title"] == "TEST"


def test_roman_heading_format():
    """Test 'XII. WAGES' format."""
    text = (
        "\n\nI. RECOGNITION\n\n"
        "Recognition text.\n\n"
        "II. MANAGEMENT RIGHTS\n\n"
        "Management text.\n\n"
        "XII. WAGES\n\n"
        "Wage text.\n"
    )
    chunks = find_articles(text)
    assert len(chunks) == 3
    assert chunks[2].number == "12"
