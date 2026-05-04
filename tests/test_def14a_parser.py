"""Tests for DEF14A director-row extraction. (24Q-12, 2026-05-03)

Uses synthetic HTML modeled on real DEF14A patterns so the test is fast
and doesn't require a network fixture. The Starbucks 2026 proxy uses the
per-director-mini-table pattern; the Apple 2024 proxy uses the big-summary-
table pattern. Both shapes are exercised here.
"""
from __future__ import annotations


from scripts.etl.load_def14a_directors import parse_directors


PER_DIRECTOR_MINITABLE_HTML = """
<html><body>
<h2>Our Directors</h2>

<table>
  <tr><td>Jane Q. Public Age 58 Director Since 2017 Lead Independent Director</td></tr>
  <tr><td>Independent</td></tr>
  <tr><td>Professional background: Former CEO of Acme Corp; serves on the
      audit and compensation committees.</td></tr>
</table>

<table>
  <tr><td>John K. Smith Age 62 Director Since 2019</td></tr>
  <tr><td>Independent</td></tr>
  <tr><td>Professional background: Founder of Smith Capital. Member of the
      nominating and governance committee.</td></tr>
</table>

<table>
  <tr>
    <th>Director</th><th>Total Compensation</th>
  </tr>
  <tr><td>Jane Q. Public</td><td>$329,921</td></tr>
  <tr><td>John K. Smith</td><td>$310,000</td></tr>
  <tr><td>Mary Wong</td><td>$280,000</td></tr>
</table>

</body></html>
"""

BIG_SUMMARY_TABLE_HTML = """
<html><body>
<h2>Director Summary</h2>
<table>
  <tr>
    <th>Name</th><th>Age</th><th>Director Since</th>
    <th>Independent</th><th>Committees</th>
  </tr>
  <tr>
    <td>Alice Brown</td><td>54</td><td>2010</td>
    <td>Yes</td><td>Audit, Compensation</td>
  </tr>
  <tr>
    <td>Bob Green</td><td>67</td><td>2003</td>
    <td>Yes</td><td>Nominating</td>
  </tr>
  <tr>
    <td>Carol White</td><td>49</td><td>2018</td>
    <td>Yes</td><td>Audit, Risk, Technology</td>
  </tr>
  <tr>
    <td>Dave Black</td><td>71</td><td>1999</td>
    <td>No</td><td>(employee)</td>
  </tr>
  <tr>
    <td>Eve Gray</td><td>55</td><td>2021</td>
    <td>Yes</td><td>Compensation, Sustainability</td>
  </tr>
</table>
</body></html>
"""


def test_per_director_minitable_extracts_names_ages_committees():
    dirs = parse_directors(PER_DIRECTOR_MINITABLE_HTML)
    by_name = {d.name.lower(): d for d in dirs}
    # Jane and John extracted from Strategy 1; Mary added by Strategy 3.
    assert "jane q. public" in by_name or "jane q public" in by_name
    jane = next(d for d in dirs if d.name.lower().startswith("jane"))
    assert jane.age == 58
    assert jane.director_since_year == 2017
    # 'Lead Independent Director' shows up in primary_occupation (not in a
    # separate 'position' field, since the 2026-05-03 regex generalization
    # to handle Starbucks + Abbott orderings dropped the per-row position.)
    assert jane.primary_occupation and "lead independent" in jane.primary_occupation.lower()
    assert jane.is_independent is True
    assert jane.compensation_total == 329921.0
    # Committees come from the bio text scan in Strategy 1
    assert {"Audit", "Compensation"}.issubset(set(jane.committees or []))


def test_per_director_minitable_attaches_compensation_via_strategy3():
    dirs = parse_directors(PER_DIRECTOR_MINITABLE_HTML)
    by_name = {d.name.lower(): d for d in dirs}
    john = next(d for d in dirs if d.name.lower().startswith("john"))
    # Strategy 3 (director comp table) merges the comp value
    assert john.compensation_total == 310000.0
    assert john.parse_strategy in ("per_director_minitable", "director_comp_table")


def test_big_summary_table_extracts_directors():
    dirs = parse_directors(BIG_SUMMARY_TABLE_HTML)
    names = sorted(d.name.lower() for d in dirs)
    assert "alice brown" in names
    assert "bob green" in names
    assert "carol white" in names
    assert "eve gray" in names
    alice = next(d for d in dirs if d.name.lower() == "alice brown")
    assert alice.age == 54
    assert alice.director_since_year == 2010
    assert alice.is_independent is True
    assert {"Audit", "Compensation"}.issubset(set(alice.committees or []))


def test_big_summary_table_marks_employee_director_not_independent():
    dirs = parse_directors(BIG_SUMMARY_TABLE_HTML)
    dave = next(d for d in dirs if d.name.lower() == "dave black")
    assert dave.is_independent is False


def test_empty_html_returns_empty_list():
    assert parse_directors("") == []
    assert parse_directors("<html><body><p>No directors here.</p></body></html>") == []


def test_no_director_table_returns_empty():
    # Tables exist but no director-shaped headers
    html = "<html><body><table><tr><th>Foo</th><th>Bar</th></tr><tr><td>1</td><td>2</td></tr></table></body></html>"
    assert parse_directors(html) == []


# Bio-paragraph strategy (Acme-United pattern: 'NAME (age N) BIO ...')
BIO_PARAGRAPH_HTML = """
<html><body>
<h2>Directors</h2>
<p>Relevant Skills Director Since
Walter C. Johnsen (age 75) Chairman of the Board and Chief Executive Officer of the Company since January 1, 2007. 1995
Richmond Y. Holden, Jr. (age 72) Mr. Holden served as President and CEO of INgageHub from 2018 to 2020. 1998
Brian S. Olschan (Age 69) President and Chief Operating Officer of the Company since January 1, 2007. 2000
</p>
</body></html>
"""


def test_bio_paragraph_strategy_extracts_named_dirs():
    dirs = parse_directors(BIO_PARAGRAPH_HTML)
    names = sorted(d.name for d in dirs)
    # Leading filler ("Relevant Skills Director Since") must be stripped from
    # the first director's name.
    assert "Walter C. Johnsen" in names
    assert "Brian S. Olschan" in names
    # Should NOT extract "Skills" or "Since Walter C. Johnsen" as a name
    assert not any("Skills" == d.name for d in dirs)
    assert not any(d.name.lower().startswith("since ") for d in dirs)


def test_bio_paragraph_extracts_age():
    dirs = parse_directors(BIO_PARAGRAPH_HTML)
    walter = next((d for d in dirs if d.name == "Walter C. Johnsen"), None)
    assert walter is not None
    assert walter.age == 75


# False-positive guard: AAR-style retirement-plan tables that mention
# 'age 65' alongside 'director' shouldn't produce phantom directors.
RETIREMENT_PLAN_HTML = """
<html><body>
<h2>Retirement Plan Provisions</h2>
<table>
  <tr><td>The Company permits voluntary retirement when an employee reaches Age 65.</td></tr>
  <tr><td>Director benefits vest fully at Age 65 or upon completion of service.</td></tr>
  <tr><td>Subsidies kick in at Age 55, accruing through Age 65 for any director.</td></tr>
</table>
</body></html>
"""


def test_retirement_plan_table_does_not_create_phantom_directors():
    # Real proxies (AAR, Air Products) embed lots of "Age 65" mentions in
    # retirement-plan tables. The validity guard must reject names that are
    # actually 'Age:' / 'Chairman' / fragments.
    dirs = parse_directors(RETIREMENT_PLAN_HTML)
    bad_names = ("Age", "Age:", "Age 65", "Chairman", "Director")
    for d in dirs:
        for bad in bad_names:
            assert bad.lower() not in d.name.lower() or len(d.name.split()) >= 2, \
                f"phantom director detected: {d.name!r}"


# ---- Profile-block strategy (24Q-12 enhancement, 2026-05-04) ----
# AEP-style: each director's data is in a single block element with leading
# name + Age + Director Since + Independent + Committees bullets.

PROFILE_BLOCK_HTML_AEP_STYLE = """
<html><body>
<h1>Nominees For Director</h1>
<div>
  Bill Fehrman Chair, President, and CEO Other Public Company Directorships:
  • None Age: 65 Prior Public Company Directorships Held in the Past Five Years:
  Director Since: August 2024 • Centuri Holdings, Inc. Independent: No
  AEP Committees: • Executive Professional Highlights Elected president and
  chief executive officer of AEP in January 2024.
</div>
<div>
  Sandra Beach Lin Other Public Company Directorships:
  • Calumet, Inc. Age: 68 Prior Public Company Directorships:
  Director Since: November 2012 • None Independent: Yes
  AEP Committees: • Audit • Executive • Nominating and Governance
  Professional Highlights Retired CEO.
</div>
</body></html>
"""


def test_profile_block_strategy_extracts_aep_style_directors():
    dirs = parse_directors(PROFILE_BLOCK_HTML_AEP_STYLE)
    by_name = {d.name.lower(): d for d in dirs}
    assert "bill fehrman" in by_name, f"missing Bill Fehrman; got {list(by_name)}"
    assert "sandra beach lin" in by_name, f"missing Sandra Beach Lin; got {list(by_name)}"
    bill = by_name["bill fehrman"]
    assert bill.age == 65
    assert bill.director_since_year == 2024
    assert bill.is_independent is False
    sandra = by_name["sandra beach lin"]
    assert sandra.age == 68
    assert sandra.director_since_year == 2012
    assert sandra.is_independent is True
    # Committee bullets parsed
    assert {"Audit", "Executive"}.issubset(set(sandra.committees or []))


# AAR-style: profile data is in one <td>, name is in a sibling <td> of the
# same <tr> (two-column layout with empty spacer cells in the middle).

PROFILE_BLOCK_HTML_AAR_STYLE = """
<html><body>
<h2>Director Nominees</h2>
<table>
<tr>
  <td>
    Chairman, President and Chief Executive Officer of AAR CORP.
    Age: 48 Director since: 2017
    Committees: • Executive
    Other public company directorships: • GATX Corporation
  </td>
  <td></td>
  <td>John M. Holmes Chairman of the Board Expertise relevant to our business
      and strategy</td>
</tr>
<tr>
  <td>
    Partner and Vice Chairman, New Vernon Capital
    Age: 64 Director since: 2024
    Committees: • Nominating and Governance (Chair) • Audit • Executive
  </td>
  <td></td>
  <td>Jeffrey N. Edwards Director Expertise relevant to our business</td>
</tr>
</table>
</body></html>
"""


def test_profile_block_strategy_extracts_aar_style_via_sibling_cell():
    # AAR-style markup puts the name in a sibling <td> of the same <tr> as
    # the profile data. The sibling-cell fallback must find it.
    dirs = parse_directors(PROFILE_BLOCK_HTML_AAR_STYLE)
    by_name = {d.name.lower(): d for d in dirs}
    assert "john m. holmes" in by_name, f"missing John M. Holmes; got {list(by_name)}"
    assert "jeffrey n. edwards" in by_name, f"missing Jeffrey N. Edwards; got {list(by_name)}"
    holmes = by_name["john m. holmes"]
    assert holmes.age == 48
    assert holmes.director_since_year == 2017
    edwards = by_name["jeffrey n. edwards"]
    assert edwards.age == 64
    assert edwards.director_since_year == 2024
    # Committees bullets
    assert "Audit" in (edwards.committees or [])
    assert "Executive" in (edwards.committees or [])


# Air-Products-style: classical big summary table but with header
# "Year First Elected or Appointed" instead of "Director Since", AND a
# leading empty spacer row + interleaved empty spacer cells.

BIG_SUMMARY_TABLE_AIRPRODUCTS_STYLE = """
<html><body>
<h2>Nominees for Election as Directors</h2>
<table>
  <tr>
    <td></td><td></td><td></td><td></td><td></td><td></td><td></td>
  </tr>
  <tr>
    <td>Name</td><td></td><td></td>
    <td>Age</td><td></td><td></td>
    <td>Year First Elected or Appointed</td><td></td><td></td>
    <td>Position</td>
  </tr>
  <tr>
    <td>Joshua S. Horowitz</td><td></td><td></td>
    <td>48</td><td></td><td></td>
    <td>2023</td><td></td><td></td>
    <td>Chairman of the Board</td>
  </tr>
  <tr>
    <td>R. Joseph Jackson</td><td></td><td></td>
    <td>60</td><td></td><td></td>
    <td>2021</td><td></td><td></td>
    <td>Vice Chairman of the Board</td>
  </tr>
  <tr>
    <td>Charles T. Lanktree</td><td></td><td></td>
    <td>76</td><td></td><td></td>
    <td>2017</td><td></td><td></td>
    <td>Director</td>
  </tr>
  <tr>
    <td>E. Gray Payne</td><td></td><td></td>
    <td>78</td><td></td><td></td>
    <td>2017</td><td></td><td></td>
    <td>Director</td>
  </tr>
  <tr>
    <td>John M. Suzuki</td><td></td><td></td>
    <td>62</td><td></td><td></td>
    <td>2021</td><td></td><td></td>
    <td>Director, Chief Executive Officer and President</td>
  </tr>
</table>
</body></html>
"""


def test_big_summary_table_handles_year_first_elected_header():
    # Air-Products-style: header is "Year First Elected or Appointed", not
    # "Director Since". And the table has a leading blank spacer row plus
    # interleaved empty spacer cells.
    dirs = parse_directors(BIG_SUMMARY_TABLE_AIRPRODUCTS_STYLE)
    names = sorted(d.name for d in dirs)
    assert "Joshua S. Horowitz" in names, f"missing Joshua; got {names}"
    assert "Charles T. Lanktree" in names, f"missing Charles; got {names}"
    assert "John M. Suzuki" in names, f"missing John; got {names}"
    josh = next(d for d in dirs if d.name == "Joshua S. Horowitz")
    assert josh.age == 48
    assert josh.director_since_year == 2023


def test_section_heading_words_rejected_as_director_names():
    # The profile-block fallback used to pick up "Information about our
    # directors" / "Proposal 1 Election of director nominees" /
    # "Professional Highlights" as director names. The expanded keyword
    # blacklist must reject these.
    from scripts.etl.load_def14a_directors import _is_valid_director_name
    bad = [
        "Information about our",
        "Proposal 1 Election",
        "Professional Highlights",
        "Class II Directors",
        "Following Information",
        "Director Nominees",
        "Continued Directors",
    ]
    for s in bad:
        assert not _is_valid_director_name(s), f"should reject {s!r}"
    # And keep accepting real names
    good = ["John M. Holmes", "Sandra Beach Lin", "Bill Fehrman",
            "R. Joseph Jackson", "E. Gray Payne"]
    for s in good:
        assert _is_valid_director_name(s), f"should accept {s!r}"
