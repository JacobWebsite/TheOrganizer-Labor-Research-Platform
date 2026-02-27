"""Unit tests for the CBA rule engine with synthetic text snippets."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.cba.models import ArticleChunk, RuleMatch
from scripts.cba.rule_engine import (
    CategoryRules,
    HeadingSignal,
    NegativePattern,
    TextPattern,
    _build_article_ref,
    _deduplicate_matches,
    _extract_modal,
    _extract_sentence_context,
    extract_context_window,
    filter_toc_index_chunks,
    is_toc_or_index_text,
    load_all_rules,
    load_category_rules,
    match_all_chunks,
    match_chunk,
    match_text_all_categories,
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

    def test_caps_at_600(self):
        text = "A" * 800
        result = _extract_sentence_context(text, 0, 800)
        assert len(result) <= 600


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
        assert any(m.provision_class == "health_insurance" for m in matches)

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
        assert any(m.provision_class == "wages_base_pay" for m in matches)

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
        assert any(m.provision_class == "overtime" for m in matches)

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
        assert any(m.provision_class == "retirement_pension" for m in matches)

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
        assert any(m.provision_class == "paid_leave" for m in matches)


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
                "ARTICLE 10 - WAGES\n\nBase hourly rate shall be $20.00.",
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
        full_text = "A" * 200 + "MATCHED PROVISION TEXT HERE" + "B" * 200
        before, after = extract_context_window(full_text, 200, 226)
        assert len(before) <= 110
        assert len(after) <= 110
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
