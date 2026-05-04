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
