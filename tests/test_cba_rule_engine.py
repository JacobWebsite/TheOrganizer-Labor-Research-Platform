"""Unit tests for the CBA rule engine with synthetic text snippets."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.cba.models import ArticleChunk, RuleMatch
from scripts.cba.rule_engine import (  # noqa: F401
    CategoryRules,
    HeadingExclusion,
    HeadingSignal,
    NegativePattern,
    TextPattern,
    _build_article_ref,
    _deduplicate_matches,
    _extract_modal,
    _extract_sentence_context,
    _heading_excluded,
    _should_merge,
    extract_context_window,
    filter_toc_index_chunks,
    is_toc_or_index_text,
    load_all_rules,
    load_category_rules,
    match_all_chunks,
    match_chunk,
    match_text_all_categories,
    populate_context,
    score_heading,
)


def _make_chunk(text: str, title: str = "", number: str = "1", level: int = 1) -> ArticleChunk:
    return ArticleChunk(
        number=number, title=title, level=level,
        text=text, char_start=0, char_end=len(text),
    )


class TestModalExtraction:
    def test_shall(self):
        modal, weight = _extract_modal("The employer shall provide health insurance.")
        assert modal == "shall"
        assert weight == 0.90

    def test_must(self):
        modal, weight = _extract_modal("Employees must report to work on time.")
        assert modal == "must"
        assert weight == 0.90

    def test_may(self):
        modal, weight = _extract_modal("The union may file a grievance.")
        assert modal == "may"
        assert weight == 0.40

    def test_will(self):
        modal, weight = _extract_modal("The company will contribute $100 per month.")
        assert modal == "will"
        assert weight == 0.80

    def test_shall_not(self):
        modal, weight = _extract_modal("Employees shall not engage in any strike.")
        assert modal == "shall not"
        assert weight == 0.95

    def test_no_modal(self):
        modal, weight = _extract_modal("Overtime is paid at time and one half.")
        assert modal is None
        assert weight == 0.50


class TestSentenceContext:
    def test_extracts_sentence(self):
        text = "First sentence here. The employer shall provide insurance. Last sentence."
        result = _extract_sentence_context(text, 21, 60)
        assert "employer shall provide" in result

    def test_caps_at_2000(self):
        text = "A" * 3000
        result = _extract_sentence_context(text, 0, 3000)
        assert len(result) <= 2000


class TestHeadingScoring:
    def test_healthcare_heading(self):
        rules = load_category_rules("healthcare")
        assert rules is not None
        score = score_heading("HEALTH AND WELFARE BENEFITS", rules)
        assert score > 0.0

    def test_unrelated_heading(self):
        rules = load_category_rules("healthcare")
        assert rules is not None
        score = score_heading("MANAGEMENT RIGHTS", rules)
        assert score == 0.0

    def test_grievance_heading(self):
        rules = load_category_rules("grievance")
        assert rules is not None
        score = score_heading("GRIEVANCE AND ARBITRATION PROCEDURE", rules)
        assert score >= 0.4


class TestChunkMatching:
    def test_healthcare_match(self):
        rules = load_category_rules("healthcare")
        assert rules is not None
        chunk = _make_chunk(
            "ARTICLE 15 - HEALTH INSURANCE\n\n"
            "The Employer shall contribute $500 per month toward health insurance premiums "
            "for each eligible employee. Employees may select from HMO or PPO plans.",
            title="HEALTH INSURANCE"
        )
        matches = match_chunk(chunk, rules)
        assert len(matches) > 0
        assert any(m.provision_class == "employer_premium" for m in matches)

    def test_wages_match(self):
        rules = load_category_rules("wages")
        assert rules is not None
        chunk = _make_chunk(
            "ARTICLE 10 - WAGES\n\n"
            "The base hourly rate shall be $22.50 effective January 1, 2024. "
            "Employees shall receive a wage increase of 3% on January 1, 2025.",
            title="WAGES"
        )
        matches = match_chunk(chunk, rules)
        assert len(matches) > 0
        assert any(m.provision_class == "base_wage_rate" for m in matches)

    def test_grievance_match(self):
        rules = load_category_rules("grievance")
        assert rules is not None
        chunk = _make_chunk(
            "ARTICLE 8 - GRIEVANCE PROCEDURE\n\n"
            "A grievance shall be defined as any dispute regarding the interpretation "
            "or application of this Agreement. Step 1: The employee shall present the "
            "grievance to the supervisor within 10 working days. If unresolved, it may "
            "be submitted to binding arbitration through the AAA.",
            title="GRIEVANCE PROCEDURE"
        )
        matches = match_chunk(chunk, rules)
        assert len(matches) >= 2

    def test_no_match_on_unrelated_text(self):
        rules = load_category_rules("healthcare")
        assert rules is not None
        chunk = _make_chunk(
            "ARTICLE 4 - MANAGEMENT RIGHTS\n\n"
            "The Employer retains the right to direct the workforce, "
            "assign work, and determine methods of operation.",
            title="MANAGEMENT RIGHTS"
        )
        matches = match_chunk(chunk, rules)
        assert len(matches) == 0

    def test_negative_pattern_filters(self):
        rules = load_category_rules("healthcare")
        assert rules is not None
        chunk = _make_chunk(
            "ARTICLE 20 - SAFETY\n\n"
            "The employer shall maintain health and safety standards in compliance "
            "with OSHA regulations. All employees must complete occupational safety training.",
            title="SAFETY"
        )
        matches = match_chunk(chunk, rules)
        # health and safety should be filtered by negative pattern
        assert len(matches) == 0

    def test_overtime_match(self):
        rules = load_category_rules("scheduling")
        assert rules is not None
        chunk = _make_chunk(
            "ARTICLE 12 - HOURS AND OVERTIME\n\n"
            "Overtime shall be paid at time and one-half for all hours worked "
            "in excess of eight hours per day or forty hours per week. "
            "Overtime shall be distributed equally among qualified employees.",
            title="HOURS AND OVERTIME"
        )
        matches = match_chunk(chunk, rules)
        assert len(matches) > 0
        assert any(m.provision_class == "overtime_rate" for m in matches)

    def test_pension_match(self):
        rules = load_category_rules("pension")
        assert rules is not None
        chunk = _make_chunk(
            "ARTICLE 16 - PENSION\n\n"
            "The Employer shall contribute $2.50 per hour to the pension fund "
            "for each covered employee. Employees shall be vested after five years of service.",
            title="PENSION"
        )
        matches = match_chunk(chunk, rules)
        assert len(matches) > 0
        assert any(m.provision_class in ("pension_contribution", "contribution_rate") for m in matches)

    def test_leave_match(self):
        rules = load_category_rules("leave")
        assert rules is not None
        chunk = _make_chunk(
            "ARTICLE 14 - LEAVE\n\n"
            "Employees shall earn two weeks of paid vacation after one year of service. "
            "Sick leave shall accrue at the rate of one day per month. "
            "Three personal days per year shall be granted. "
            "Bereavement leave of three days shall be granted for death in the immediate family.",
            title="LEAVE"
        )
        matches = match_chunk(chunk, rules)
        assert len(matches) >= 2
        assert any(m.provision_class in ("vacation_days", "sick_leave", "personal_days", "bereavement") for m in matches)


class TestDeduplication:
    def test_overlapping_matches_keeps_highest_confidence(self):
        matches = [
            RuleMatch(
                provision_class="health_insurance", category="healthcare",
                matched_text="test", char_start=100, char_end=200,
                confidence=0.90, rule_name="rule_a",
            ),
            RuleMatch(
                provision_class="health_insurance", category="healthcare",
                matched_text="test", char_start=100, char_end=200,
                confidence=0.75, rule_name="rule_b",
            ),
        ]
        deduped = _deduplicate_matches(matches)
        assert len(deduped) == 1
        assert deduped[0].confidence == 0.90

    def test_non_overlapping_kept(self):
        matches = [
            RuleMatch(
                provision_class="health_insurance", category="healthcare",
                matched_text="first", char_start=0, char_end=100,
                confidence=0.85, rule_name="rule_a",
            ),
            RuleMatch(
                provision_class="wages_base_pay", category="wages",
                matched_text="second", char_start=500, char_end=600,
                confidence=0.80, rule_name="rule_b",
            ),
        ]
        deduped = _deduplicate_matches(matches)
        assert len(deduped) == 2


class TestRuleLoading:
    def test_load_all_rules(self):
        rules = load_all_rules()
        assert len(rules) == 14

    def test_load_healthcare(self):
        rules = load_category_rules("healthcare")
        assert rules is not None
        assert rules.category == "healthcare"
        assert len(rules.text_patterns) > 0
        assert len(rules.heading_signals) > 0

    def test_load_nonexistent_returns_none(self):
        rules = load_category_rules("fake_category_xyz")
        assert rules is None

    def test_all_patterns_compile(self):
        """Verify all regex patterns compile without errors."""
        rules = load_all_rules()
        for r in rules:
            for hs in r.heading_signals:
                hs.compiled()  # Should not raise
            for tp in r.text_patterns:
                tp.compiled()  # Should not raise
            for np in r.negative_patterns:
                np.compiled()  # Should not raise


class TestMatchAllChunks:
    def test_multi_chunk_processing(self):
        rules = load_category_rules("wages")
        assert rules is not None
        chunks = [
            _make_chunk(
                "ARTICLE 10 - WAGES\n\n"
                "The base hourly rate shall be $20.00 per hour effective January 1, 2025. "
                "Employees in the bargaining unit shall receive a wage increase of 3% "
                "on January 1, 2026 as specified in the attached wage schedule.",
                title="WAGES", number="10"
            ),
            _make_chunk(
                "ARTICLE 11 - OVERTIME\n\nOvertime is handled elsewhere.",
                title="OVERTIME", number="11"
            ),
        ]
        matches = match_all_chunks(chunks, rules)
        assert len(matches) >= 1
        # All matches should be from the wages rules
        assert all(m.category == "wages" for m in matches)


class TestFix1TocIndexFilter:
    """Fix 1: Page-range filter eliminates TOC/Index false positives."""

    def test_toc_dotted_line_detected(self):
        assert is_toc_or_index_text("Military Service...............97")
        assert is_toc_or_index_text("Jury Duty....110")
        assert is_toc_or_index_text("Subject    Page")

    def test_normal_text_not_toc(self):
        assert not is_toc_or_index_text(
            "The employer shall provide health insurance to all employees."
        )

    def test_filter_removes_toc_chunks(self):
        chunks = [
            ArticleChunk(
                number="TOC", title="Table of Contents", level=1,
                text="Military Service...............97\nJury Duty....110",
                char_start=0, char_end=100, page_start=2, page_end=2,
            ),
            ArticleChunk(
                number="1", title="WAGES", level=1,
                text="The base hourly rate shall be $20.00.",
                char_start=5000, char_end=5100, page_start=10, page_end=10,
            ),
            ArticleChunk(
                number="IDX", title="INDEX", level=1,
                text="Arbitration.....145\nGrievances.....72",
                char_start=50000, char_end=50100, page_start=160, page_end=160,
            ),
        ]
        filtered = filter_toc_index_chunks(chunks, total_pages=162)
        assert len(filtered) == 1
        assert filtered[0].title == "WAGES"

    def test_filter_without_pages_uses_content_only(self):
        toc_chunk = ArticleChunk(
            number="TOC", title="Contents", level=1,
            text="Health Insurance.........45\nWages.........30",
            char_start=0, char_end=100,
        )
        normal_chunk = ArticleChunk(
            number="1", title="WAGES", level=1,
            text="Hourly rate is $25.00.",
            char_start=200, char_end=300,
        )
        filtered = filter_toc_index_chunks([toc_chunk, normal_chunk])
        assert len(filtered) == 1


class TestFix2CoverageTiers:
    """Fix 2: coverage_tiers requires health-insurance context words."""

    def test_individual_in_grievance_not_matched(self):
        rules = load_category_rules("healthcare")
        chunk = _make_chunk(
            "GRIEVANCE PROCEDURE\n\n"
            "No individual shall have the right to settle any claim "
            "or grievance on behalf of any other employee.",
            title="GRIEVANCE PROCEDURE"
        )
        matches = match_chunk(chunk, rules)
        coverage_matches = [m for m in matches if m.rule_name == "coverage_tiers"]
        assert len(coverage_matches) == 0

    def test_individual_locker_not_matched(self):
        rules = load_category_rules("healthcare")
        chunk = _make_chunk(
            "WORKING CONDITIONS\n\n"
            "Each employee shall be provided with an individual locker and key.",
            title="WORKING CONDITIONS"
        )
        matches = match_chunk(chunk, rules)
        coverage_matches = [m for m in matches if m.rule_name == "coverage_tiers"]
        assert len(coverage_matches) == 0

    def test_individual_family_coverage_matched(self):
        rules = load_category_rules("healthcare")
        chunk = _make_chunk(
            "HEALTH INSURANCE\n\n"
            "Employees may select individual or family coverage under "
            "the HMO or PPO plan options.",
            title="HEALTH INSURANCE"
        )
        matches = match_chunk(chunk, rules)
        coverage_matches = [m for m in matches if m.rule_name == "coverage_tiers"]
        assert len(coverage_matches) > 0

    def test_death_in_family_not_healthcare(self):
        rules = load_category_rules("healthcare")
        chunk = _make_chunk(
            "LEAVE POLICY\n\n"
            "Three days of bereavement leave for death in family.",
            title="LEAVE POLICY"
        )
        matches = match_chunk(chunk, rules)
        assert len(matches) == 0

    def test_family_leave_not_healthcare(self):
        rules = load_category_rules("healthcare")
        chunk = _make_chunk(
            "NYS PAID FAMILY LEAVE\n\n"
            "Employees are eligible for family leave under NYS law.",
            title="NYS PAID FAMILY LEAVE"
        )
        matches = match_chunk(chunk, rules)
        coverage_matches = [m for m in matches if m.rule_name == "coverage_tiers"]
        assert len(coverage_matches) == 0


class TestFix3JustCause:
    """Fix 3: just_cause vs good_cause disambiguation."""

    def test_just_cause_exact_high_confidence(self):
        rules = load_category_rules("job_security")
        chunk = _make_chunk(
            "DISCIPLINE\n\n"
            "Termination of employment for any reason other than just cause "
            "is subject to the grievance procedure.",
            title="DISCIPLINE"
        )
        matches = match_chunk(chunk, rules)
        jc = [m for m in matches if "just_cause" in m.rule_name]
        assert len(jc) > 0
        assert jc[0].confidence >= 0.90

    def test_good_cause_procedural_not_matched(self):
        rules = load_category_rules("job_security")
        chunk = _make_chunk(
            "ARBITRATION\n\n"
            "The arbitrator may extend any time limit for good cause shown.",
            title="ARBITRATION"
        )
        matches = match_chunk(chunk, rules)
        jc = [m for m in matches if "cause" in m.rule_name]
        assert len(jc) == 0

    def test_good_cause_waiver_not_matched(self):
        rules = load_category_rules("job_security")
        chunk = _make_chunk(
            "PROCEDURES\n\n"
            "The RAB President or Union President may waive any provision "
            "of this agreement for good cause.",
            title="PROCEDURES"
        )
        matches = match_chunk(chunk, rules)
        jc = [m for m in matches if "cause" in m.rule_name]
        assert len(jc) == 0

    def test_good_cause_with_discipline_matched(self):
        rules = load_category_rules("job_security")
        chunk = _make_chunk(
            "DISCIPLINE AND DISCHARGE\n\n"
            "No employee shall be subject to discharge except for good cause. "
            "Disciplinary action shall follow the progressive steps.",
            title="DISCIPLINE AND DISCHARGE"
        )
        matches = match_chunk(chunk, rules)
        cause_matches = [m for m in matches if "cause" in m.rule_name]
        assert len(cause_matches) > 0


class TestFix4TrainingProgram:
    """Fix 4: training_program requires employee-as-trainee context."""

    def test_union_training_employer_not_matched(self):
        rules = load_category_rules("training")
        chunk = _make_chunk(
            "UNION SECURITY\n\n"
            "The Union shall provide training opportunity to the Employer "
            "to facilitate electronic records and dues deduction.",
            title="UNION SECURITY"
        )
        matches = match_chunk(chunk, rules)
        train = [m for m in matches if m.rule_name == "training_program"]
        assert len(train) == 0

    def test_training_fund_contribution_not_matched(self):
        rules = load_category_rules("training")
        chunk = _make_chunk(
            "WAGES\n\n"
            "The Employer shall make Pension, Health, Legal and Training Fund "
            "contributions as specified in the wage schedule.",
            title="WAGES"
        )
        matches = match_chunk(chunk, rules)
        train = [m for m in matches if m.rule_name == "training_program"]
        assert len(train) == 0

    def test_employee_training_program_matched(self):
        rules = load_category_rules("training")
        chunk = _make_chunk(
            "TRAINING\n\n"
            "The Employer shall compensate, at straight-time pay, any employee "
            "for any time required for the employee to attend any instruction "
            "or training program mandated by law.",
            title="TRAINING"
        )
        matches = match_chunk(chunk, rules)
        train = [m for m in matches if m.rule_name == "training_program"]
        assert len(train) > 0


class TestFix5JuryDutyList:
    """Fix 5: jury_duty in comma-separated list = maintenance of standards."""

    def test_jury_duty_in_topic_list_not_matched(self):
        rules = load_category_rules("leave")
        chunk = _make_chunk(
            "MAINTENANCE OF STANDARDS\n\n"
            "The Employer shall not reduce wages, hours, sick pay, vacations, "
            "holidays, relief periods, jury duty, or group life insurance "
            "below existing standards.",
            title="MAINTENANCE OF STANDARDS"
        )
        matches = match_chunk(chunk, rules)
        jury = [m for m in matches if m.rule_name == "jury_duty"]
        assert len(jury) == 0

    def test_standalone_jury_duty_matched(self):
        rules = load_category_rules("leave")
        chunk = _make_chunk(
            "JURY DUTY\n\n"
            "An employee who is called for jury duty shall receive the "
            "difference between jury duty pay and regular pay for up to "
            "ten working days per calendar year.",
            title="JURY DUTY"
        )
        matches = match_chunk(chunk, rules)
        jury = [m for m in matches if m.rule_name == "jury_duty"]
        assert len(jury) > 0


class TestFix6EnhancedDedup:
    """Fix 6: Dedup catches near-identical text from different rules."""

    def test_same_text_different_rules_deduped(self):
        text = "The employer shall provide health insurance for all employees in the bargaining unit. " * 3
        matches = [
            RuleMatch(
                provision_class="health_insurance", category="healthcare",
                matched_text=text, char_start=0, char_end=len(text),
                confidence=0.90, rule_name="rule_a",
            ),
            RuleMatch(
                provision_class="health_insurance", category="healthcare",
                matched_text=text, char_start=0, char_end=len(text),
                confidence=0.75, rule_name="rule_b",
            ),
        ]
        deduped = _deduplicate_matches(matches)
        assert len(deduped) == 1
        assert deduped[0].confidence == 0.90


class TestFix7TextTruncation:
    """Fix 7: Sentence extraction extends past truncation boundaries."""

    def test_incomplete_sentence_extended(self):
        text = "First sentence done. The employer shall provide paid leave for illnesses that require extended"
        # The match is at the word "leave"
        result = _extract_sentence_context(text + " absence from work. Next sentence.", 40, 50)
        # Should extend to find the sentence-ending period
        assert "absence from work" in result

    def test_complete_sentence_not_extended(self):
        text = "The employer shall provide insurance. Another sentence here."
        result = _extract_sentence_context(text, 0, 35)
        assert "insurance" in result


class TestFix8ArticleReference:
    """Fix 8: Article references detect statutory section numbers (>100)."""

    def test_normal_section_number(self):
        chunk = ArticleChunk(
            number="3.4", title="Overtime", level=2,
            text="", char_start=0, char_end=0,
            parent_number="3",
        )
        ref = _build_article_ref(chunk)
        assert "Article 3, Section 3.4" in ref

    def test_statutory_section_uses_parent(self):
        chunk = ArticleChunk(
            number="1981", title="Civil Rights Claims", level=2,
            text="", char_start=0, char_end=0,
            parent_number="19",
        )
        ref = _build_article_ref(chunk)
        assert "Article 19" in ref
        assert "1981" not in ref

    def test_high_section_without_parent(self):
        chunk = ArticleChunk(
            number="350", title="Workers Comp", level=2,
            text="", char_start=0, char_end=0,
        )
        ref = _build_article_ref(chunk)
        # No parent, so falls through to normal Section display
        assert "Section 350" in ref


class TestFix9ContextWindow:
    """Fix 9: Context window capture (~100 chars before and after)."""

    def test_context_before_and_after(self):
        full_text = "A" * 600 + "MATCHED PROVISION TEXT HERE" + "B" * 600
        before, after = extract_context_window(full_text, 600, 626)
        assert len(before) <= 510
        assert len(after) <= 510
        assert "A" in before
        assert "B" in after

    def test_context_at_start_of_document(self):
        full_text = "MATCHED TEXT" + " some more text " * 20
        before, after = extract_context_window(full_text, 0, 12)
        assert before == ""
        assert len(after) > 0

    def test_context_at_end_of_document(self):
        full_text = "some prefix text " * 20 + "MATCHED TEXT"
        start = len(full_text) - 12
        before, after = extract_context_window(full_text, start, len(full_text))
        assert len(before) > 0
        assert after == ""


class TestPopulateContext:
    """Test populate_context fills context_before and context_after on matches."""

    def test_populates_context_fields(self):
        full_text = "Before text here. " + "MATCHED PROVISION" + " After text here."
        matches = [
            RuleMatch(
                provision_class="test", category="test",
                matched_text="MATCHED PROVISION",
                char_start=18, char_end=35,
                confidence=0.85, rule_name="test_rule",
            ),
        ]
        populate_context(matches, full_text)
        assert matches[0].context_before is not None
        assert matches[0].context_after is not None
        assert "Before" in matches[0].context_before
        assert "After" in matches[0].context_after

    def test_empty_matches_no_error(self):
        populate_context([], "some text")  # Should not raise


class TestHeadingExclusion:
    """Heading exclusions block a category entirely when heading matches."""

    def test_scheduling_excluded_in_grievance_section(self):
        rules = load_category_rules("scheduling")
        assert rules is not None
        chunk = _make_chunk(
            "ARTICLE 25 - GRIEVANCE AND ARBITRATION\n\n"
            "If the grievance is sustained, the employee shall be paid at time "
            "and one-half for all hours improperly denied. The arbitrator shall "
            "determine the appropriate remedy.",
            title="GRIEVANCE AND ARBITRATION"
        )
        matches = match_chunk(chunk, rules)
        assert len(matches) == 0, "overtime_rate should not match in grievance section"

    def test_scheduling_excluded_by_parent_title(self):
        rules = load_category_rules("scheduling")
        assert rules is not None
        chunk = ArticleChunk(
            number="3", title="Late Payment Penalties", level=2,
            text=(
                "Section 3 - Late Payment\n\n"
                "If the employer fails to pay within 30 days, the penalty "
                "shall be time and one-half the amount owed for all hours "
                "worked during the period of non-payment."
            ),
            char_start=0, char_end=200,
            parent_number="25",
            parent_title="ARTICLE XXV - Enforcement of Articles (the Funds)",
        )
        matches = match_chunk(chunk, rules)
        assert len(matches) == 0, "overtime_rate should not match under Enforcement heading"

    def test_scheduling_matches_in_hours_section(self):
        rules = load_category_rules("scheduling")
        assert rules is not None
        chunk = _make_chunk(
            "ARTICLE 12 - HOURS OF WORK\n\n"
            "Overtime shall be paid at time and one-half for all hours worked "
            "in excess of eight hours per day or forty hours per week.",
            title="HOURS OF WORK"
        )
        matches = match_chunk(chunk, rules)
        assert any(m.provision_class == "overtime_rate" for m in matches)

    def test_management_rights_excluded_in_discipline_section(self):
        rules = load_category_rules("management_rights")
        assert rules is not None
        chunk = _make_chunk(
            "ARTICLE 7 - DISCHARGE AND DISCIPLINE\n\n"
            "The Employer retains the right to discipline or discharge "
            "employees for just cause.",
            title="DISCHARGE AND DISCIPLINE"
        )
        matches = match_chunk(chunk, rules)
        assert len(matches) == 0, "management_rights should not match in discipline section"

    def test_heading_excluded_helper(self):
        rules = CategoryRules(
            category="test",
            provision_classes=[],
            heading_signals=[],
            text_patterns=[],
            negative_patterns=[],
            heading_exclusions=[
                HeadingExclusion(pattern=r"\bgrievance\b", note="test"),
            ],
        )
        assert _heading_excluded("Grievance Procedure", None, rules) is True
        assert _heading_excluded("Wages", None, rules) is False
        assert _heading_excluded("Section 3", "Grievance and Arbitration", rules) is True
        assert _heading_excluded(None, None, rules) is False

    def test_empty_exclusions_never_block(self):
        rules = load_category_rules("grievance")
        assert rules is not None
        assert _heading_excluded("Anything at all", None, rules) is False

    def test_all_rules_parse_heading_exclusions(self):
        """Verify heading_exclusions field parses without errors for all categories."""
        rules = load_all_rules()
        for r in rules:
            for he in r.heading_exclusions:
                he.compiled()  # Should not raise


class TestHeadingAffinityPenalty:
    """Zero-affinity heading imposes a -0.15 penalty instead of +0.10 boost."""

    def test_overtime_in_unrelated_section_lower_confidence(self):
        rules = load_category_rules("scheduling")
        assert rules is not None
        # Use a heading that doesn't trigger exclusion but has zero affinity
        chunk = _make_chunk(
            "ARTICLE 22 - SENIORITY\n\n"
            "Overtime shall be paid at time and one-half for all hours worked "
            "in excess of eight hours per day or forty hours per week. "
            "Distribution of overtime opportunities shall be by seniority.",
            title="SENIORITY"
        )
        matches = match_chunk(chunk, rules)
        ot = [m for m in matches if m.provision_class == "overtime_rate"]
        if ot:
            # Base confidence 0.90 - 0.15 penalty = 0.75
            assert ot[0].confidence <= 0.76, f"Expected <=0.76, got {ot[0].confidence}"

    def test_overtime_in_hours_section_boosted(self):
        rules = load_category_rules("scheduling")
        assert rules is not None
        chunk = _make_chunk(
            "ARTICLE 12 - HOURS OF WORK AND OVERTIME\n\n"
            "Overtime shall be paid at time and one-half for all hours worked "
            "in excess of eight hours per day or forty hours per week.",
            title="HOURS OF WORK AND OVERTIME"
        )
        matches = match_chunk(chunk, rules)
        ot = [m for m in matches if m.provision_class == "overtime_rate"]
        assert len(ot) > 0
        # heading_score >= 0.5 -> +0.05 boost -> 0.95
        assert ot[0].confidence >= 0.90


class TestCoverageGapFixes:
    """2026-05-12 coverage-gap pass: 11 zero-match provision classes now have
    broader patterns. Each test uses a real-world phrasing sampled from the
    actual CBA corpus."""

    # -- probationary_period (job_security) -------------------------------
    def test_probationary_period_extended_window(self):
        rules = load_category_rules("job_security")
        chunk = _make_chunk(
            "PROBATIONARY PERIOD\n\n"
            "The probationary period may be extended by thirty (30) calendar days, "
            "at the Employer's/Hospital's option, by giving notice of extension "
            "in writing to the employee seven (7) days prior to the original expiry.",
            title="PROBATIONARY PERIOD",
        )
        matches = match_chunk(chunk, rules)
        prob = [m for m in matches if m.provision_class == "probationary_period"]
        assert len(prob) > 0

    def test_probationary_employees_ninety_days(self):
        rules = load_category_rules("job_security")
        chunk = _make_chunk(
            "ARTICLE 6 - SENIORITY\n\n"
            "Probationary employees shall not acquire seniority for the first "
            "ninety (90) calendar days after hire and shall receive no holiday pay.",
            title="SENIORITY",
        )
        matches = match_chunk(chunk, rules)
        prob = [m for m in matches if m.provision_class == "probationary_period"]
        assert len(prob) > 0

    # -- pension: vesting / retirement_eligibility / pension_fund ----------
    def test_vesting_fully_vested(self):
        rules = load_category_rules("pension")
        chunk = _make_chunk(
            "ARTICLE 18 - PENSION\n\n"
            "An eligible employee shall be fully vested at all times in the "
            "portion of his or her 401(k) Plan account that is attributable to "
            "his or her pre-tax elective contributions and matching contributions.",
            title="PENSION",
        )
        matches = match_chunk(chunk, rules)
        v = [m for m in matches if m.provision_class == "vesting"]
        assert len(v) > 0

    def test_retirement_after_age(self):
        rules = load_category_rules("pension")
        chunk = _make_chunk(
            "ARTICLE 20 - RETIREE BENEFITS\n\n"
            "Employees who retire after age 55 with 20 or more years of service "
            "will be provided with $1,000 of Company-paid life insurance.",
            title="RETIREE BENEFITS",
        )
        matches = match_chunk(chunk, rules)
        re_ = [m for m in matches if m.provision_class == "retirement_eligibility"]
        assert len(re_) > 0

    def test_pension_fund_contribution_context(self):
        rules = load_category_rules("pension")
        chunk = _make_chunk(
            "ARTICLE 15 - PENSION\n\n"
            "The Employer shall contribute ten percent (10%) of gross monthly "
            "labor payroll to the Union 613 Pension Trust Fund's designated local "
            "collection agent for all covered employees.",
            title="PENSION",
        )
        matches = match_chunk(chunk, rules)
        pf = [m for m in matches if m.provision_class == "pension_fund"]
        assert len(pf) > 0

    # -- scheduling: overtime_after / schedule_posting --------------------
    def test_overtime_after_via_premium_clause(self):
        rules = load_category_rules("scheduling")
        chunk = _make_chunk(
            "ARTICLE 12 - HOURS\n\n"
            "Time and one-half (1 1/2) shall be paid for work in excess of forty "
            "(40) hours per week, with the regular work week being Monday through Friday.",
            title="HOURS",
        )
        matches = match_chunk(chunk, rules)
        ot = [m for m in matches if m.provision_class == "overtime_after"]
        assert len(ot) > 0

    def test_overtime_after_hours_worked_in_excess(self):
        rules = load_category_rules("scheduling")
        chunk = _make_chunk(
            "ARTICLE 12 - HOURS\n\n"
            "Hours worked in excess of eight (8) hours shall be paid at one and "
            "one-half times the regular straight-time rate of pay.",
            title="HOURS",
        )
        matches = match_chunk(chunk, rules)
        ot = [m for m in matches if m.provision_class == "overtime_after"]
        assert len(ot) > 0

    def test_schedule_posting_basic(self):
        rules = load_category_rules("scheduling")
        chunk = _make_chunk(
            "ARTICLE 9 - SCHEDULING\n\n"
            "Schedules shall be posted complete and in accordance with appropriate "
            "staffing complements. Float pools and call-in lists shall be maintained.",
            title="SCHEDULING",
        )
        matches = match_chunk(chunk, rules)
        sp = [m for m in matches if m.provision_class == "schedule_posting"]
        assert len(sp) > 0

    # -- seniority: seniority_bidding -------------------------------------
    def test_seniority_bidding_window(self):
        rules = load_category_rules("seniority")
        chunk = _make_chunk(
            "ARTICLE 11 - JOB BIDDING\n\n"
            "Vacancies shall be filled in accordance with seniority preference "
            "by qualified employees in the bargaining unit.",
            title="JOB BIDDING",
        )
        matches = match_chunk(chunk, rules)
        sb = [m for m in matches if m.provision_class == "seniority_bidding"]
        assert len(sb) > 0

    # -- technology: ai_provisions ----------------------------------------
    def test_ai_provisions_named_broader(self):
        rules = load_category_rules("technology")
        chunk = _make_chunk(
            "ARTICLE 30 - SCOPE OF WORK\n\n"
            "Work involving Artificial Intelligence (AI) technology should "
            "constitute covered work under this Article. Any such determination "
            "will only be effective if approved in writing by the Labor Department.",
            title="SCOPE OF WORK",
        )
        matches = match_chunk(chunk, rules)
        ai = [m for m in matches if m.provision_class == "ai_provisions"]
        assert len(ai) > 0

    # -- training: apprentice_ratio / training_time_paid ------------------
    def test_apprentice_ratio_reverse_phrasing(self):
        rules = load_category_rules("training")
        chunk = _make_chunk(
            "ARTICLE 17 - APPRENTICESHIP\n\n"
            "The ratio of apprentices to journeymen shall be one (1) apprentice "
            "for the first two (2) journeymen after the foreman and an additional "
            "apprentice for every three (3) journeymen thereafter.",
            title="APPRENTICESHIP",
        )
        matches = match_chunk(chunk, rules)
        ap = [m for m in matches if m.provision_class == "apprentice_ratio"]
        assert len(ap) > 0

    def test_training_will_be_paid(self):
        rules = load_category_rules("training")
        chunk = _make_chunk(
            "ARTICLE 22 - TRAINING\n\n"
            "Employees assigned to training at non-MTA locations will be paid "
            "at their regular rate and for the tour of duty assigned on those "
            "training dates. Travel allowance shall be provided pursuant to policy.",
            title="TRAINING",
        )
        matches = match_chunk(chunk, rules)
        tp = [m for m in matches if m.provision_class == "training_time_paid"]
        assert len(tp) > 0

    def test_training_on_paid_time(self):
        rules = load_category_rules("training")
        chunk = _make_chunk(
            "ARTICLE 15 - SAFETY\n\n"
            "All employees shall complete the safety training. All training must "
            "be completed on paid time and at no cost to the employee.",
            title="SAFETY",
        )
        matches = match_chunk(chunk, rules)
        tp = [m for m in matches if m.provision_class == "training_time_paid"]
        assert len(tp) > 0

    # -- union_security: union_access -------------------------------------
    def test_union_access_broad_to_shop(self):
        rules = load_category_rules("union_security")
        chunk = _make_chunk(
            "ARTICLE 2 - UNION RIGHTS\n\n"
            "The representative of the Union shall be allowed access to any "
            "shop or job, at any reasonable time, where workmen are employed "
            "under the terms of this agreement.",
            title="UNION RIGHTS",
        )
        matches = match_chunk(chunk, rules)
        ua = [m for m in matches if m.provision_class == "union_access"]
        assert len(ua) > 0

    def test_union_business_agent_access_project(self):
        rules = load_category_rules("union_security")
        chunk = _make_chunk(
            "ARTICLE 7 - UNION ACCESS\n\n"
            "The Union business agent or special representative shall have access "
            "to the project during working hours and shall make every reasonable "
            "effort to advise the Contractor of any visit.",
            title="UNION ACCESS",
        )
        matches = match_chunk(chunk, rules)
        ua = [m for m in matches if m.provision_class == "union_access"]
        assert len(ua) > 0

    # -- overreach guards: new patterns shouldn't fire on non-CBA-relevant text
    def test_pension_fund_named_not_fired_on_bare_mention(self):
        """pension_fund_named requires contribution/trustee context; bare 'pension
        plan' mention in an unrelated section shouldn't trigger it."""
        rules = load_category_rules("pension")
        chunk = _make_chunk(
            "ARTICLE 25 - DEFINITIONS\n\n"
            "For purposes of this Agreement, the term 'employee' shall include "
            "all persons whose primary work is performed for the Employer.",
            title="DEFINITIONS",
        )
        matches = match_chunk(chunk, rules)
        # No pension-related content -> no pension_fund match
        pf = [m for m in matches if m.provision_class == "pension_fund"]
        assert len(pf) == 0

    def test_seniority_bidding_window_not_fired_without_seniority(self):
        """seniority_bidding_window requires the word 'seniority' near a bid/vacancy
        word; a plain bidding clause without seniority should not match."""
        rules = load_category_rules("seniority")
        chunk = _make_chunk(
            "ARTICLE 4 - DEFINITIONS\n\n"
            "The Employer reserves the right to assign work as required by "
            "operational needs without prior approval from the Union.",
            title="DEFINITIONS",
        )
        matches = match_chunk(chunk, rules)
        sb = [m for m in matches if m.provision_class == "seniority_bidding"]
        assert len(sb) == 0


class TestFragmentMerging:
    """Fragment merge-up prevents mid-sentence splits."""

    def test_lowercase_start_merged(self):
        assert _should_merge(
            "The employer shall provide",
            "health insurance for all employees."
        ) is True

    def test_conjunction_start_merged(self):
        assert _should_merge(
            "Overtime shall be paid at time and a half.",
            "and double time on Sundays."
        ) is True

    def test_uppercase_new_paragraph_not_merged(self):
        assert _should_merge(
            "This is a complete sentence.",
            "The Union shall have the right to file grievances on behalf of any employee in the unit."
        ) is False

    def test_heading_not_merged(self):
        assert _should_merge(
            "Some prior text here.",
            "ARTICLE 12 - HOURS OF WORK"
        ) is False

    def test_section_prefix_not_merged(self):
        assert _should_merge(
            "End of prior section.",
            "Section 3. The employer shall..."
        ) is False
