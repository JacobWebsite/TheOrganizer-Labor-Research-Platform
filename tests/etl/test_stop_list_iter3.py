"""Unit tests for stop-list iter 3 additions (2026-05-18).

Iter 3 expands ``scripts/etl/sec_10k/extract_relationship_entities.py``'s
stop-list to filter 10 new categories of false-positive entity mentions
surfaced by Agent 6's 5/18 coverage report:

1. Trailing " The Company" (PATTERN) -- sentence-boundary captures that
   span a heading into the next sentence's subject (33 hits flagged).
2. Cloud-service-model acronyms (EXACT): SaaS, PaaS, IaaS.
3. OEM / OEMs (EXACT) -- already covered by iter 1, retained as a
   regression guard.
4. Engineering / sales channel acronyms (EXACT): EPC, ECS.
5. Banking / regulatory acronyms (EXACT): CET1, BHC, SCB, GHG.
6. Polymer codes (EXACT): PTFE, PVC, PET, PP, PE.
7. Aviation / standards bodies (EXACT): IATA, NDC, AIA.
8. Retail-channel boilerplate (EXACT): Order Pickup, Drive Up.
9. Sentence-initial adverbs (PATTERN with corp-suffix override):
   Substantial, Synthetic, Significant.
10. Federal Reserve regulator (PATTERN with negative lookahead) -- veto
    "Federal Reserve" alone but allow "Federal Reserve Bank of <city>".

Each category gets:
  * Positive case(s): the boilerplate term IS filtered (returns False).
  * Overreach guard(s): a real-firm name CONTAINING the term IS NOT
    filtered (returns True). This is the key invariant; cf. the iter 2
    overreach guards for Salesforce / Canadian Pacific Railway in
    ``test_sec_10k_extract_entities.py``.

These tests exercise the regex / heuristic surface only -- no DB.
"""
from __future__ import annotations


from scripts.etl.sec_10k import extract_relationship_entities as ext


# --------------------------------------------------------------------------
# 1. Trailing "The Company" (PATTERN)
# --------------------------------------------------------------------------


def test_trailing_the_company_is_filtered():
    """Sentence-boundary capture: 'Service Group\\nThe Company concentrates'
    -> 'Service Group The Company' -- the trailing fragment is not a
    real entity. Iter 2 stop-listed one literal phrase ('raw materials
    the company'); iter 3 generalizes to any mention ending in
    ' The Company'.
    """
    assert not ext._is_acceptable_entity("Service Group The Company")
    assert not ext._is_acceptable_entity("Operating Segment The Company")
    assert not ext._is_acceptable_entity("Distribution Network The Company")
    # Capitalization variants of "the Company" (the regex is
    # case-insensitive on the trailing fragment).
    assert not ext._is_acceptable_entity("Marketing Plan the company")


def test_trailing_the_company_overreach_guard():
    """A real company name that doesn't end in 'The Company' must pass,
    even if 'The Company' appears EARLIER in the mention (which would
    only happen pathologically -- but we want to be sure the anchor
    matters).
    """
    # Normal mid-mention captures must pass.
    assert ext._is_acceptable_entity("Walmart Inc")
    assert ext._is_acceptable_entity("The Coca-Cola Company")  # 'Company'
                                                                # at end is
                                                                # OK -- only
                                                                # ' The Company'
                                                                # trailing
                                                                # fragment is
                                                                # vetoed.


# --------------------------------------------------------------------------
# 2. SaaS / PaaS / IaaS (EXACT)
# --------------------------------------------------------------------------


def test_cloud_service_model_acronyms_filtered():
    """'Our SaaS customers include...' -- SaaS the acronym is a generic
    category, not a firm.
    """
    for term in ("SaaS", "PaaS", "IaaS", "saas", "paas", "iaas"):
        assert not ext._is_acceptable_entity(term), term


def test_saas_capital_overreach_guard():
    """'Saas Capital' is a real BDC (business-development company) that
    funds SaaS firms. The exact-match set is case-folded so 'saas' the
    acronym is filtered, but 'Saas Capital' is multi-token and survives.
    """
    assert ext._is_acceptable_entity("Saas Capital")
    assert ext._is_acceptable_entity("Saas Capital Inc")


# --------------------------------------------------------------------------
# 3. OEM / OEMs (EXACT) -- regression guard from iter 1
# --------------------------------------------------------------------------


def test_oem_acronyms_remain_filtered_regression_guard():
    """Agent 6's 5/18 report flagged OEM/OEMs but iter 1 (2026-05-10)
    already stop-listed them. This test pins the iter 1 entries so a
    future stop-list edit can't accidentally drop them.
    """
    for term in ("OEM", "OEMs", "oem", "oems"):
        assert not ext._is_acceptable_entity(term), term


# --------------------------------------------------------------------------
# 4. EPC / ECS (EXACT)
# --------------------------------------------------------------------------


def test_engineering_channel_acronyms_filtered():
    """EPC = Engineering/Procurement/Construction, ECS = Electronic
    Control System. Both appear as generic-category mentions in
    industrial 10-Ks.
    """
    for term in ("EPC", "ECS", "epc", "ecs"):
        assert not ext._is_acceptable_entity(term), term


def test_epc_overreach_guard():
    """'EPC Industries Inc' (hypothetical) should pass since the
    exact-match set only blocks the bare acronym.
    """
    assert ext._is_acceptable_entity("EPC Industries Inc")
    assert ext._is_acceptable_entity("ECS Federal Inc")  # real fed contractor


# --------------------------------------------------------------------------
# 5. CET1 / BHC / SCB / GHG (EXACT) -- banking / regulatory
# --------------------------------------------------------------------------


def test_banking_regulatory_acronyms_filtered():
    """CET1 = Common Equity Tier 1, BHC = Bank Holding Company,
    SCB = Stress Capital Buffer, GHG = greenhouse gas. None are firms.
    """
    for term in ("CET1", "BHC", "SCB", "GHG", "cet1", "bhc", "scb", "ghg"):
        assert not ext._is_acceptable_entity(term), term


def test_banking_acronyms_overreach_guard():
    """Real co names containing these acronyms should still pass."""
    # BHC could appear as a ticker-style mention; multi-token is fine.
    assert ext._is_acceptable_entity("BHC Securities Inc")
    # GHG Controls Inc (hypothetical industrial firm).
    assert ext._is_acceptable_entity("GHG Solutions LLC")


# --------------------------------------------------------------------------
# 6. PTFE / PVC / PET / PP / PE (EXACT) -- polymer codes
# --------------------------------------------------------------------------


def test_polymer_codes_filtered():
    """Material codes (PTFE, PVC, PET, PP, PE). All appear as
    generic-category mentions in chemical / materials 10-Ks.
    """
    # >= 3-char codes always go through the EXACT check.
    for term in ("PTFE", "PVC", "PET", "ptfe", "pvc", "pet"):
        assert not ext._is_acceptable_entity(term), term
    # 2-char codes (PP, PE) are also length-filtered earlier (< 3 chars),
    # but we add them to _STOP_EXACT defensively in case the length
    # rule changes. Single-character or 2-char inputs hit the len(s) < 3
    # guard before _STOP_EXACT.
    assert not ext._is_acceptable_entity("PP")
    assert not ext._is_acceptable_entity("PE")


def test_pvc_overreach_guard():
    """'PVC Industries Inc' is a real co (hypothetical / generic naming
    pattern); should pass.
    """
    assert ext._is_acceptable_entity("PVC Industries Inc")
    assert ext._is_acceptable_entity("PET Manufacturing Corp")
    # PTFE Solutions Group (real-ish; corp-suffix anchored).
    assert ext._is_acceptable_entity("PTFE Solutions Group")


# --------------------------------------------------------------------------
# 7. IATA / NDC / AIA (EXACT) -- aviation / standards
# --------------------------------------------------------------------------


def test_aviation_standards_acronyms_filtered():
    """IATA = Int'l Air Transport Assoc., NDC = New Distribution
    Capability, AIA = Aerospace Industries Assoc. All show up in
    airline / aerospace 10-Ks as protocol/body mentions, not firms.
    """
    for term in ("IATA", "NDC", "AIA", "iata", "ndc", "aia"):
        assert not ext._is_acceptable_entity(term), term


def test_aia_overreach_guard():
    """'AIA Group' (the Hong Kong insurance holding company) is a real
    public firm. Should still pass because the exact-match set only
    blocks the bare acronym.
    """
    assert ext._is_acceptable_entity("AIA Group Limited")
    # NDC Health (real healthcare IT firm circa 2000s; corp-suffix
    # anchored).
    assert ext._is_acceptable_entity("NDC Health Corp")


# --------------------------------------------------------------------------
# 8. Order Pickup / Drive Up (EXACT) -- retail boilerplate
# --------------------------------------------------------------------------


def test_retail_channel_boilerplate_filtered():
    """'Order Pickup' / 'Drive Up' are standard Target / Walmart
    fulfillment-channel labels that get captured as proper-noun phrases.
    """
    for term in ("Order Pickup", "Drive Up", "order pickup", "drive up"):
        assert not ext._is_acceptable_entity(term), term


def test_retail_channel_overreach_guard():
    """A real firm with 'Drive' or 'Pickup' in its name should pass."""
    # Hypothetical: real co's like 'Pickup Plus Inc' / 'Drive Holdings'.
    assert ext._is_acceptable_entity("Pickup Plus Inc")
    assert ext._is_acceptable_entity("Drive Holdings LLC")


# --------------------------------------------------------------------------
# 9. Sentence-initial Substantial / Synthetic / Significant (PATTERN)
# --------------------------------------------------------------------------


def test_sentence_initial_adverbs_filtered_when_alone():
    """Bare 'Substantial' / 'Synthetic' / 'Significant' at the start of
    a regex-captured phrase is sentence-starter noise, not a firm name.
    """
    assert not ext._is_acceptable_entity("Substantial")
    assert not ext._is_acceptable_entity("Synthetic")
    assert not ext._is_acceptable_entity("Significant")
    # With trailing common-noun (still no corp anchor) -- still vetoed.
    assert not ext._is_acceptable_entity("Substantial doubt exists")
    assert not ext._is_acceptable_entity("Synthetic risk")
    assert not ext._is_acceptable_entity("Significant customer")


def test_sentence_initial_adverbs_overreach_guard_corp_suffix():
    """Real co names that start with these adverbs but include a corp
    suffix (Inc / Corp / LLC / Holdings / Group / etc.) must still pass.
    The corp-suffix override is what distinguishes 'Significant Beauty
    Holdings' (a real firm) from 'Significant customer concentrations'
    (prose).
    """
    assert ext._is_acceptable_entity("Significant Beauty Holdings")
    assert ext._is_acceptable_entity("Synthetic Industries Inc")
    assert ext._is_acceptable_entity("Substantial Capital Group")
    # Corp-suffix override is anywhere in the phrase, not just the end.
    assert ext._is_acceptable_entity("Synthetic Genomics Inc")


def test_sentence_initial_adverbs_only_anchor_leading_token():
    """The veto only fires on the LEADING token. Mid-phrase
    'significant' (lowercase or capitalized inside a longer phrase)
    should NOT trigger the veto.
    """
    # "Hercules Significant Holdings" -- 'Significant' is the middle
    # token, not the leading one. Pattern requires '^Significant\\b',
    # so this passes.
    assert ext._is_acceptable_entity("Hercules Significant Holdings")
    # Lowercase 'significant' anywhere in the phrase is not matched
    # (pattern is case-sensitive). The phrase still has to clear the
    # other filters; with a corp suffix it does.
    assert ext._is_acceptable_entity("Acme significant Inc")


# --------------------------------------------------------------------------
# 10. Federal Reserve (PATTERN with negative lookahead)
# --------------------------------------------------------------------------


def test_federal_reserve_bare_is_filtered():
    """'Federal Reserve' alone is the central-bank regulator, not a
    target firm.
    """
    assert not ext._is_acceptable_entity("Federal Reserve")
    assert not ext._is_acceptable_entity("Federal Reserve System")
    assert not ext._is_acceptable_entity("Federal Reserve Board")


def test_federal_reserve_bank_overreach_guard():
    """Negative lookahead `(?!\\s+bank)` lets the regional Federal
    Reserve Bank entities through -- they're large employers that
    organizers may target.
    """
    assert ext._is_acceptable_entity("Federal Reserve Bank of Boston")
    assert ext._is_acceptable_entity("Federal Reserve Bank of New York")
    assert ext._is_acceptable_entity("Federal Reserve Bank of San Francisco")
    assert ext._is_acceptable_entity("Federal Reserve Bank of Chicago")


# --------------------------------------------------------------------------
# Cross-cutting: iter 3 entries don't regress iter 1 / iter 2 cases
# --------------------------------------------------------------------------


def test_iter3_does_not_regress_iter1_iter2_real_companies():
    """The iter 1 / iter 2 test suite already proves 'Salesforce' /
    'Canadian Pacific Railway' / 'New York Times Company' / etc. pass.
    These overreach-guard names should still pass after iter 3 lands.
    """
    iter1_iter2_overreach_names = [
        "Salesforce",
        "Salesforce.com Inc",
        "Fortune Brands Innovations",
        "Canadian Pacific Railway",
        "Itemize Inc",
        "FormFactor Inc",
        "Los Angeles Times Communications LLC",
        "New York Life Insurance Company",
        "New York Times Company",
        "DTC Industries Inc",
        "HIV Research Foundation",
        "Asia Pacific Wire & Cable Corporation",
    ]
    for name in iter1_iter2_overreach_names:
        assert ext._is_acceptable_entity(name), name


def test_iter3_stop_pattern_collection_has_three_entries():
    """Sanity check: the _STOP_PATTERN collection has the three iter 3
    PATTERN entries (trailing The Company, sentence-initial adverbs,
    Federal Reserve negative-lookahead). This guards against accidental
    drop of an entry during future refactors.
    """
    assert len(ext._STOP_PATTERN) == 3, ext._STOP_PATTERN
    # Each entry is (compiled_regex, allow_corp_suffix_override: bool).
    for pat, allow_corp in ext._STOP_PATTERN:
        assert hasattr(pat, "search"), pat
        assert isinstance(allow_corp, bool), allow_corp


def test_iter3_stop_exact_includes_all_new_entries():
    """Pin the new exact-match additions so a future stop-list cleanup
    doesn't accidentally drop them.
    """
    expected_iter3_exact = {
        # Cloud-service-model acronyms.
        "saas", "paas", "iaas",
        # Engineering / channel acronyms.
        "epc", "ecs",
        # Banking / regulatory acronyms.
        "cet1", "bhc", "scb", "ghg",
        # Polymer codes.
        "ptfe", "pvc", "pet", "pp", "pe",
        # Aviation / standards bodies.
        "iata", "ndc", "aia",
        # Retail-channel boilerplate.
        "order pickup", "drive up",
    }
    missing = expected_iter3_exact - ext._STOP_EXACT
    assert not missing, f"iter 3 _STOP_EXACT entries missing: {missing}"
