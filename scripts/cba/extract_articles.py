"""Extract articles from a CBA contract by heading detection.

Simple approach: find ARTICLE/Section headings, split text between them,
store each article with its full text in cba_sections.

Handles multiple heading formats:
  ARTICLE I / ARTICLE XIV    (roman numerals)
  ARTICLE 1 / ARTICLE 22     (arabic numerals)
  Article 1 / Article 22     (mixed case)
  Section 1 / SECTION 5      (fallback for contracts without ARTICLE headings)

Deduplicates TOC entries: when the same article number appears in both
a Table of Contents (short, <50 words) and the actual body, keeps only
the body version.

Usage:
    py scripts/cba/extract_articles.py --cba-id 26
    py scripts/cba/extract_articles.py --cba-id 26 --dry-run
    py scripts/cba/extract_articles.py --all --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection

# Heading patterns in priority order -- first match wins per contract
# Each entry is (pattern, min_matches) -- per-pattern minimums avoid false positives
HEADING_PATTERNS = [
    # ARTICLE with roman numerals (e.g., ARTICLE XIV)
    (re.compile(
        r"^[ \t]*(ARTICLE\s+[IVXLCDM]+[A-Z]?)\s*[-.:]*\s*(.*)$",
        re.MULTILINE | re.IGNORECASE,
    ), 3),
    # ARTICLE with arabic numerals (e.g., ARTICLE 14, Article 3)
    (re.compile(
        r"^[ \t]*(ARTICLE\s+\d+)\s*[-.:]*\s*(.*)$",
        re.MULTILINE | re.IGNORECASE,
    ), 3),
    # ARTICLE with spelled-out numbers (e.g., Article One, Article Twenty-Three)
    (re.compile(
        r"^[ \t]*(ARTICLE\s+[A-Z][a-z]+(?:[\s-][A-Z]?[a-z]+)*)\s*[-.:]*\s*(.*)$",
        re.MULTILINE,
    ), 3),
    # Section as fallback (e.g., Section 1, SECTION 5) -- higher minimum to avoid
    # false positives on contracts that use inline "Section 8.6(a)" references
    (re.compile(
        r"^[ \t]*(Section\s+\d+)\s*[-.:]*\s*(.*)$",
        re.MULTILINE | re.IGNORECASE,
    ), 5),
    # SECTION with roman numerals (e.g., SECTION I--RECOGNITION, SECTION III - WAGES)
    (re.compile(
        r"^[ \t]*(SECTION\s+[IVXLCDM]+)\s*[-.:]*\s*(.*)$",
        re.MULTILINE | re.IGNORECASE,
    ), 3),
    # Standalone roman numeral headings (e.g., I. RECOGNITION, XII. Wages)
    (re.compile(
        r"^[ \t]*([IVXLCDM]+)\.\s+([A-Z][A-Za-z\s,&/()\-.']{2,75})$",
        re.MULTILINE,
    ), 5),
    # Bare numbered headings (e.g., 1. Recognition, 2. Management Rights)
    (re.compile(
        r"^[ \t]*(\d{1,2})\.\s+([A-Z][A-Za-z\s,&/()\-.']{3,75})$",
        re.MULTILINE,
    ), 5),
    # SECTION with decimal numbering (e.g., SECTION 1.1 TERM OF AGREEMENT)
    (re.compile(
        r"^[ \t]*(Section\s+\d+\.\d+)\s*[-.:]*\s*(.*)$",
        re.MULTILINE | re.IGNORECASE,
    ), 5),
]

# Category tags based on article title keywords
# Plain substring/stem matching -- no word boundaries needed
CATEGORY_MAP = [
    (r"recognition|union\s+security|dues|check[\s-]?off|membership", "union_security"),
    (r"joint\s+industry|advancement\s+project|joint\s+committee|labor[\s-]management|joint\s+conference|joint\s+labor|management.*cooperation|labor.*management\s+(?:meet|committee)", "joint_industry"),
    (r"management\s+right|employer\s+right|rights?\s+of\s+(?:the\s+)?employer|managements?\s+right|management\s+function|management\b(?!\s*(?:and|/))", "management_rights"),
    (r"no\s+strike|no\s+lockout|no\s+work\s+stoppage|strike.*lockout|lockout.*strike|work\s+stoppage", "no_strike"),
    (r"health\s+(?:and|&)\s+safety|safety\s+(?:and|&)\s+health|OSHA", "safety"),
    (r"coverage|scope|bargaining\s+unit|unit\s+designat|territory|jurisdiction|definition\s+of\s+work|employees\s+covered", "coverage"),
    (r"overtime", "overtime"),
    (r"wage|hour|compensation|pay\s+rate|salar(?:y|ies)|minimum|cost\s+of\s+living|COLA|stipend|economic\s+package|rates?\s+of\s+pay|call[\s-]?in\s+pay|report(?:ing)?\s+pay", "wages_hours"),
    (r"working\s+condition|working\s+rule|work\s+rule|general\s+work|lunch|rest\s+period|break|teaching\s+cond|show\s+up|standby|call\s*back|light\s+duty|on[\s-]call|work\s+year|time\s+requirement|use\s+of\s+facilit|tools\b|general\s+condition|rules\s+and\s+regulat|out\s+of\s+title|productivity", "working_conditions"),
    (r"grievance|mediation|dispute|problem\s+solv|adjustment\s+of", "grievance"),
    (r"arbitration|system\s+board\s+of\s+adjust", "arbitration"),
    (r"layoff|reduction\s+(?:in|of)\s+force|seniority|bumping|recall|job\s+security|employment\s+security|re[\s-]?employment|furlough|eligibility\s+list", "job_security"),
    (r"discharge|disciplin|dismissal|corrective\s+action|investigation", "discipline"),
    (r"pension|retirement|401", "pension"),
    (r"health|welfare|benefit|insurance|fringe|medical\s+exam|medical\s+separat|reasonable\s+accommodat|rehabilitat|dental\s+plan|employee\s+assist|EAP", "benefits"),
    (r"disability|work.?incurred|injur.*illness", "disability"),
    (r"sick", "sick_leave"),
    (r"holiday", "holidays"),
    (r"vacation", "vacations"),
    (r"shift|differential", "shifts"),
    (r"schedul", "scheduling"),
    (r"leave|PTO|bereavement|paid\s+time\s+off|jury\s+duty|time\s+off|attendance|absence", "leave"),
    (r"probation|new\s+hire", "probation"),
    (r"temporary\s+employee|temporary\s+worker", "temporary_employees"),
    (r"apprentice", "apprenticeship"),
    (r"training|professional\s+develop|tuition|orientation|employee\s+develop|staff\s+develop|continuing\s+educat", "training"),
    (r"uniform|protective\s+clothing|PPE", "uniforms"),
    (r"severance", "severance"),
    (r"child\s*care|dependent\s+care", "childcare"),
    (r"discriminat|discrimnation|equal\s+opportun|EEO|equal\s+employ|respectful.*treatment|fair\s+treatment", "non_discrimination"),
    (r"past\s+practice|maintenance\s+of\s+standard", "past_practices"),
    (r"steward", "steward"),
    (r"foreman|foreperson", "foreman"),
    (r"subcontract|subletting|contracting\s+out|outsourc", "subcontracting"),
    (r"travel|mileage|moving\s+expens", "travel"),
    (r"classif|job\s+class|employee\s+class|job\s+award|position\s+description|job\s+descript", "classifications"),
    (r"superintendent|supervisor", "superintendents"),
    (r"signatory", "signatory"),
    (r"new\s+development", "new_development"),
    (r"educational\s+assist|education\s+fund|scholarship", "training"),
    (r"meal|food\s+allow|employee\s+meal", "working_conditions"),
    (r"termination\s+allow|terminal\s+pay|terminal\s+leave", "severance"),
    (r"one[\s-]time\s+payment|lump[\s-]sum|bonus|signing\s+bonus", "wages_hours"),
    (r"staffing|staff\s+level|manning|crew\s+size", "working_conditions"),
    (r"aid\s+to\s+other\s+union|mutual\s+aid", "union_security"),
    (r"class\s+size|caseload|workload", "working_conditions"),
    (r"trust\s+fund|fund\s+payment", "benefits"),
    (r"longevity", "wages_hours"),
    (r"pay\s+equity|comparable\s+worth", "wages_hours"),
    (r"domestic\s+partner|civil\s+union", "benefits"),
    (r"flexible\s+spending|FSA|HSA|health\s+savings", "benefits"),
    (r"skilled\s+trade|trainee\s+program", "training"),
    (r"compassionate|hardship", "leave"),
    (r"drinking\s+water|clothes\s+room|locker", "working_conditions"),
    (r"general\s+clause|miscellaneous|general\s+provision|general\s+employ|other\s+agree|special\s+condition|special\s+payment|supersede|parties\b|supplemental\s+agree|favored\s+nation|general\b$", "general"),
    (r"building\s+acquisition|public\s+authority|condemnation", "building_acquisition"),
    (r"term\b|duration|renewal|expir|effective\s+date|tenure\s+of\s+agree|acceptance\s+of\s+agree|termination\s+of\s+agree|terms?\s+of\s+agree", "duration"),
    (r"successor", "successorship"),
    (r"separab|severab|legality|savings|partial\s+invalid|effect\s+of\s+l(?:aw|egislat)|saving\s+clause|subordinat.*agreement|enactment|effect\s+of\s+(?:the\s+)?agree", "separability"),
    (r"technology|electronic|surveillance|telework|monitor", "technology"),
    (r"drug|alcohol|substance\s+abuse", "drug_alcohol"),
    (r"housing", "housing"),
    (r"political", "political_activity"),
    (r"negotiat|reopener", "negotiations"),
    (r"transfer|reassign", "transfers"),
    (r"evaluat|performance\s+review|appraisal", "evaluation"),
    (r"calendar", "calendar"),
    (r"pay\s+period|pay\s*day|disbursement|direct\s+deposit|payroll\s+deduct", "pay_period"),
    (r"personnel\s+record|personnel\s+file|records\b", "personnel_records"),
    (r"employee\s+right|union\s+right|worker\s+right|rights\s+of\s+the\s+part|responsibilities\s+and\s+right", "employee_rights"),
    (r"union\s+represent|union\s+access|visitation|bulletin\s+board|official\s+time|association\s+right|union\s+business|union\s+activit|representation\b", "union_access"),
    (r"waiver|zipper|entire\s+agreement", "waiver"),
    (r"purpose|preamble|declaration\s+of\s+principle|intent\s+(?:and|of)", "preamble"),
    (r"vacanc|promotion|merit\s+promot|selection\s+of\s+personnel|filling\s+of|position.*appointment|employment\b|job\s+opening", "vacancies"),
    (r"referral|hiring\s+hall", "referral"),
    (r"parking|facilit(?:y|ies)\s+and\s+suppl", "working_conditions"),
    (r"indemnif", "general"),
    (r"definition", "general"),
    (r"resignat|voluntary\s+terminat|job\s+abandon|agreement\b$|addend", "general"),
    (r"surety\s+bond|fund\s+audit|report.*contribut", "general"),
]


def _is_garbage_heading(title: str) -> bool:
    """Detect OCR artifacts and sentence fragments that aren't real article titles.

    Returns True if the title looks like garbage and should be merged into
    the previous article rather than treated as a new one.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", title)
    # Too short after stripping punctuation (e.g., "(A)", "1.", "' r  '- ''")
    if len(cleaned) < 3:
        return True
    # Pure numbers (e.g., "1", "2", "4 9 -", "8 1 -")
    if re.match(r"^[\d\s\-]+$", cleaned):
        return True
    # Starts with lowercase — likely a sentence fragment, not a heading
    # (e.g., "of this Agreement, the Company shall", "and Article 5 of this")
    stripped = title.lstrip(" \t'\"")
    if stripped and stripped[0].islower():
        return True
    # Starts with a section/clause reference mid-sentence (e.g., "section 8.6(a)")
    if re.match(r"^(?:section|clause)\s+\d+\.\d+", stripped, re.IGNORECASE):
        return True
    # Starts with a parenthetical reference like "(a)(17)" or "(D)(2)"
    if re.match(r"^\([a-zA-Z0-9]+\)\s*\(", stripped):
        return True
    # Looks like a sentence continuation: starts with a capital letter followed
    # by a period-delimited reference (e.g., "A.1, above.", "G.5.a above.")
    if re.match(r"^[A-Z]\.\d+", stripped):
        return True
    # Continuation marker like "-CONTD." or "CONTD"
    if re.match(r"^-?\s*CONTD", stripped, re.IGNORECASE):
        return True
    # Starts with comma (sentence fragment)
    if stripped.startswith(","):
        return True
    # "SECTION 1" without a title — these are sub-sections, not articles
    if re.match(r"^SECTION\s+\d+\s*$", stripped, re.IGNORECASE):
        return True
    # Ends with a period and looks like a sentence fragment
    if stripped.endswith(".") and len(stripped.split()) > 8:
        return True
    # Starts with a digit (likely a TOC line like "2   Recognized Holidays   10")
    if stripped and stripped[0].isdigit():
        return True
    # Long title (7+ words) starting with a function word -- sentence fragment
    # (e.g., "So long as the generation plant switch gear remains")
    words = stripped.split()
    if len(words) >= 7 and re.match(
        r"^(?:So|As|If|In|On|At|To|Or|An|But|For|Nor|Yet|The|That|This|"
        r"Such|Each|When|Where|Which|While|After|Before|Until|During|"
        r"However|Provided|Notwithstanding|Except|Unless)\b",
        stripped,
    ):
        return True
    return False


# Body-text fallback patterns for articles whose title didn't match.
# These are high-precision patterns: only fire if the body strongly indicates
# the category (multiple keywords or very specific phrases).
BODY_FALLBACK_MAP = [
    (r"grievance.*(?:step\s+\d|arbitrat)|file\s+a\s+grievance|grievance\s+procedure", "grievance"),
    (r"(?:shall\s+not\s+)?strike|work\s+stoppage|lockout|picket", "no_strike"),
    (r"seniority\s+(?:list|right|shall)|order\s+of\s+seniority|layoff.*seniority", "job_security"),
    (r"discharge|just\s+cause|progressive\s+disciplin|disciplinary\s+action", "discipline"),
    (r"overtime\s+(?:rate|pay|shall|work)|time\s+and\s+one[\s-]half", "overtime"),
    (r"hourly\s+(?:rate|wage)|wage\s+(?:rate|schedule|scale)|pay\s+(?:rate|grade|scale)", "wages_hours"),
    (r"health\s+(?:insurance|plan|benefit)|medical\s+(?:plan|coverage|benefit)|dental|vision\s+(?:plan|coverage)", "benefits"),
    (r"pension\s+(?:plan|fund|benefit)|retirement\s+(?:plan|fund|benefit)|401\s*\(?\s*k", "pension"),
    (r"(?:paid|unpaid)\s+leave|maternity|paternity|FMLA|family.*medical\s+leave", "leave"),
    (r"(?:annual|paid)\s+vacation|vacation\s+(?:day|pay|time|entitlement)", "vacations"),
    (r"holiday\s+(?:pay|schedule)|paid\s+holiday|(?:legal|national)\s+holiday", "holidays"),
    (r"safety\s+(?:committee|equipment|rule|standard)|protective\s+equipment|PPE", "safety"),
    (r"management\s+(?:shall\s+have|retains|reserves)\s+the\s+right", "management_rights"),
    (r"union\s+(?:shop|membership|dues)|agency\s+(?:fee|shop)|check[\s-]?off", "union_security"),
    (r"subcontract|contract(?:ing)?\s+out|outside\s+contractor", "subcontracting"),
]


def tag_article(title: str, body_text: str = "") -> str:
    """Tag an article with a category based on its title, with body-text fallback."""
    for pattern, category in CATEGORY_MAP:
        if re.search(pattern, title, re.IGNORECASE):
            return category

    # Second pass: check body text for strong category signals
    if body_text:
        # Only check first 2000 chars to keep it fast
        snippet = body_text[:2000]
        for pattern, category in BODY_FALLBACK_MAP:
            if re.search(pattern, snippet, re.IGNORECASE):
                return category

    return "other"


def _parse_number(label: str) -> tuple[str, int]:
    """Extract the display number and sort-order int from a heading label.

    Handles both 'ARTICLE XIV' (roman) and 'ARTICLE 14' (arabic).
    """
    num_part = re.sub(r"(?i)^(?:article|section)\s+", "", label).strip()

    # Try arabic first
    m = re.match(r"(\d+)", num_part)
    if m:
        return num_part, int(m.group(1))

    # Try roman
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    result = 0
    prev = 0
    for ch in reversed(num_part.upper()):
        val = values.get(ch, 0)
        if val < prev:
            result -= val
        else:
            result += val
        prev = val
    return num_part, result if result > 0 else 0


def _find_headings(text: str) -> list[re.Match]:
    """Try each heading pattern in priority order, return the first that works.

    A pattern must produce enough non-garbage headings to be accepted.
    Rejects patterns whose first heading appears after the halfway point
    (appendix-only matches) or where all good headings are garbage.
    """
    text_len = len(text)
    for pattern, min_matches in HEADING_PATTERNS:
        matches = list(pattern.finditer(text))
        if len(matches) < min_matches:
            continue
        # Quality check: count how many titles are non-garbage
        good = 0
        for m in matches:
            title = m.group(2).strip()
            title = re.sub(r"[^a-zA-Z0-9\s,&/()\-.']+", "", title).strip()
            title = re.sub(r"\.{3,}\s*\d*$", "", title).strip()
            if not _is_garbage_heading(title):
                good += 1
        if good < min_matches:
            continue
        # Coverage check: first heading should start in the first half
        # of the document to avoid appendix-only matches
        if matches[0].start() > text_len * 0.5:
            continue
        return matches
    return []


def _deduplicate_articles(articles: list[dict]) -> list[dict]:
    """When the same article number appears twice (TOC + body), keep the longer one."""
    by_number: dict[str, list[dict]] = {}
    for art in articles:
        key = art["number"].upper().strip()
        by_number.setdefault(key, []).append(art)

    deduped = []
    for key, group in by_number.items():
        if len(group) == 1:
            deduped.append(group[0])
        else:
            # Keep the longest version (body, not TOC)
            best = max(group, key=lambda a: len(a["text"]))
            deduped.append(best)

    # Sort by char_start to preserve document order
    deduped.sort(key=lambda a: a["char_start"])
    return deduped


def extract_articles(cba_id: int, dry_run: bool = False) -> dict:
    """Extract articles from a single contract."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT full_text, employer_name_raw, union_name_raw, "
                "effective_date, expiration_date, page_count "
                "FROM cba_documents WHERE cba_id = %s",
                [cba_id],
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return {"cba_id": cba_id, "error": "No full_text found"}

            text, employer, union, eff_date, exp_date, page_count = row

    # Find headings (tries roman, then arabic, then Section)
    matches = _find_headings(text)
    if not matches:
        return {"cba_id": cba_id, "error": "No article headings found", "employer": employer}

    # Build article list
    articles = []
    skipped_garbage = 0
    chars_per_page = len(text) // max(page_count or 1, 1)

    for i, m in enumerate(matches):
        art_label = m.group(1).strip()
        art_title = m.group(2).strip()
        # Clean OCR artifacts from title
        art_title = re.sub(r"[^a-zA-Z0-9\s,&/()\-.']+", "", art_title).strip()
        # Clean dotted leaders from TOC titles
        art_title = re.sub(r"\.{3,}\s*\d*$", "", art_title).strip()

        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        # Garbage heading: merge its text into the previous article
        if _is_garbage_heading(art_title):
            skipped_garbage += 1
            if articles:
                # Extend previous article to cover this section's text
                articles[-1]["text"] = text[articles[-1]["char_start"]:end].strip()
                articles[-1]["char_end"] = end
                page_end = end // chars_per_page + 1 if chars_per_page else None
                articles[-1]["page_end"] = page_end
                # Update word/char counts
            continue

        display_num, sort_num = _parse_number(art_label)
        body = text[start:end].strip()
        category = tag_article(art_title, body)

        page_start = start // chars_per_page + 1 if chars_per_page else None
        page_end = end // chars_per_page + 1 if chars_per_page else None

        articles.append({
            "number": display_num,
            "int_number": sort_num,
            "title": art_title,
            "category": category,
            "text": body,
            "char_start": start,
            "char_end": end,
            "page_start": page_start,
            "page_end": page_end,
        })

    # Deduplicate TOC entries
    articles = _deduplicate_articles(articles)

    # Detect and split mega-articles (abnormally long, likely swallowed remainder)
    if len(articles) > 2:
        lengths = [len(a["text"]) for a in articles]
        median_len = sorted(lengths)[len(lengths) // 2]
        threshold = max(20000, median_len * 10)

        new_articles = []
        for art in articles:
            if len(art["text"]) > threshold:
                # Try to find all-caps sub-headings within the mega-article body
                body = art["text"]
                sub_matches = list(re.finditer(
                    r"\n[ \t]*\n[ \t]*([A-Z][A-Z\s,&/()\-.']{3,75})[ \t]*\n",
                    body
                ))
                sub_headings = [
                    m for m in sub_matches
                    if m.group(1).strip().isupper()
                    and len(m.group(1).strip().split()) >= 2
                    and not _is_garbage_heading(m.group(1).strip())
                ]

                if len(sub_headings) >= 3:
                    for j, sm in enumerate(sub_headings):
                        rel_start = sm.start()
                        rel_end = sub_headings[j + 1].start() if j + 1 < len(sub_headings) else len(body)
                        sub_title = sm.group(1).strip()
                        sub_body = body[rel_start:rel_end].strip()
                        sub_category = tag_article(sub_title, sub_body)
                        abs_start = art["char_start"] + rel_start
                        abs_end = art["char_start"] + rel_end

                        new_articles.append({
                            "number": f"{art['number']}-{j+1}",
                            "int_number": art["int_number"] * 100 + j + 1,
                            "title": sub_title,
                            "category": sub_category,
                            "text": sub_body,
                            "char_start": abs_start,
                            "char_end": abs_end,
                            "page_start": abs_start // chars_per_page + 1 if chars_per_page else None,
                            "page_end": abs_end // chars_per_page + 1 if chars_per_page else None,
                        })
                    print(f"  Split mega-article '{art['title']}' ({len(body):,} chars) into {len(sub_headings)} sub-articles")
                else:
                    new_articles.append(art)
                    print(f"  WARNING: mega-article '{art['title']}' ({len(body):,} chars) - no sub-headings found, keeping as-is")
            else:
                new_articles.append(art)
        articles = new_articles

    result = {
        "cba_id": cba_id,
        "employer": employer,
        "union": union,
        "effective_date": str(eff_date) if eff_date else None,
        "expiration_date": str(exp_date) if exp_date else None,
        "article_count": len(articles),
        "skipped_garbage": skipped_garbage,
        "articles": articles,
    }

    if not dry_run:
        _save_articles(cba_id, articles)

    return result


def _save_articles(cba_id: int, articles: list[dict]) -> None:
    """Save articles to cba_sections, replacing any existing rows."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cba_sections WHERE cba_id = %s", [cba_id])

            for art in articles:
                attrs = {
                    "category": art["category"],
                    "word_count": len(art["text"].split()),
                    "char_count": len(art["text"]),
                }
                cur.execute(
                    """INSERT INTO cba_sections (
                        cba_id, section_num, section_title, section_level,
                        sort_order, section_text, char_start, char_end,
                        page_start, page_end, detection_method, attributes
                    ) VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s, %s, 'article_heading', %s)
                    """,
                    [
                        cba_id, art["number"], art["title"],
                        art["int_number"], art["text"],
                        art["char_start"], art["char_end"],
                        art["page_start"], art["page_end"],
                        json.dumps(attrs),
                    ],
                )
            conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract articles from CBA contracts")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cba-id", type=int, help="Single contract")
    group.add_argument("--all", action="store_true", help="All contracts")
    parser.add_argument("--dry-run", action="store_true", help="Print only, no DB changes")
    args = parser.parse_args()

    if args.cba_id:
        cba_ids = [args.cba_id]
    else:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT cba_id FROM cba_documents "
                    "WHERE full_text IS NOT NULL ORDER BY cba_id"
                )
                cba_ids = [r[0] for r in cur.fetchall()]

    total_articles = 0
    total_other = 0
    total_garbage = 0

    for cba_id in cba_ids:
        result = extract_articles(cba_id, dry_run=args.dry_run)

        if result.get("error"):
            print(f"CBA {cba_id}: {result['error']}")
            continue

        articles = result["articles"]
        other_count = sum(1 for a in articles if a["category"] == "other")
        garbage = result.get("skipped_garbage", 0)
        total_articles += len(articles)
        total_other += other_count
        total_garbage += garbage

        print(f"CBA {cba_id}: {result['employer']} / {result['union']}")
        print(f"  {result['article_count']} articles ({other_count} tagged 'other', {garbage} garbage headings merged)")

        for art in articles:
            words = len(art["text"].split())
            print(f"    {art['number']:>5s}: {art['title'][:55]:<55s}  [{art['category']:<20s}]  {words:>5,}w")

        if args.dry_run:
            print("  DRY RUN")
        else:
            print("  Saved to cba_sections")
        print()

    pct = total_other * 100 // max(total_articles, 1)
    print(f"Total: {total_articles} articles, {total_other} tagged 'other' ({pct}%), {total_garbage} garbage headings merged")


if __name__ == "__main__":
    main()
