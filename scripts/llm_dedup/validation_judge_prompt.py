"""
Unified entity-resolution judge prompt for the 2026-04-21 validation batch.

Design goals vs. dedup_judge_prompt.py (v1.0):
  - Covers BOTH dedup pairs and hierarchy pairs in one prompt.
  - Returns structured reasoning (primary_signal + supporting_signals) so we
    can mine the output for new rule candidates.
  - Padded to >=2048 tokens so Haiku 4.5 prompt caching activates. After the
    first request, subsequent requests read the cached prompt at 10% of the
    input-token price -- roughly 50% total cost reduction on input side.
  - Expanded verdict taxonomy to express hierarchy relationships that v1 could
    not (SIBLING, PARENT_CHILD, BROKEN).

Output schema -- machine-parsable JSON, single line, no markdown fences:
  {
    "label": "DUPLICATE|RELATED|SIBLING|PARENT_CHILD|UNRELATED|BROKEN",
    "confidence": "HIGH|MEDIUM|LOW",
    "primary_signal": "<one key from the enumerated signal list>",
    "supporting_signals": ["<0-3 additional signal keys>"],
    "reasoning": "<<=200 chars plain-English explanation>"
  }

The enumerated signal list is the KEY TO RULE MINING. Every verdict must pick
one primary_signal from the list below. New rule candidates are discovered by
clustering (label, primary_signal) tuples: whenever >=30 pairs share the same
(label, primary_signal) and >=95% have the same label, that's a candidate
deterministic rule we can port into rule_engine.py.
"""

# Bumped per revision for result attribution.
PROMPT_VERSION = "v2.0-validation"

JUDGE_MODEL = "claude-haiku-4-5-20251001"
MAX_OUTPUT_TOKENS = 300  # v1 was 250; v2 returns structured signals

# The enumerated signal list (must stay stable; mining clusters by exact string).
# Any new primary_signal values returned by Haiku that don't match will cluster
# as "_unknown" -- those are worth inspecting but should stay rare.
PRIMARY_SIGNAL_ENUM = [
    # Name-based signals
    "name_byte_identical",           # Exact string match after case-fold
    "name_punctuation_only_diff",    # Differ only by punctuation/commas/&
    "name_suffix_only_diff",         # Differ only by LLC/Inc/Corp/LP suffix
    "name_minor_variant",            # Typos, abbreviations, spacing
    "name_token_overlap",            # Significant shared tokens but not all
    "name_prefix_match",             # One is a prefix of the other
    "name_brand_prefix_only",        # Only share brand prefix (Morgan Stanley X vs Y)

    # Structural ID signals
    "ein_match",                     # Same federal tax ID
    "ein_conflict",                  # Both have EINs and they differ
    "ein_prefix_match",              # Same first 2-3 digits of EIN (IRS region)
    "phone_match",                   # Same phone number
    "website_match",                 # Same canonical domain

    # Location signals
    "address_full_match",            # Full street address match
    "address_minus_suite_match",     # Same building, diff suite/unit
    "zip_match",                     # Same 5-digit ZIP
    "zip_city_match",                # Same ZIP + city (without address)
    "city_state_match",              # Same city + state only
    "geographic_mismatch",           # Different cities or states

    # Structural pattern signals
    "series_number",                 # "Fund N" / "Series N" / "Trust N" pattern
    "chapter_structure",             # "American Legion Post N" / "Local N"
    "chain_location",                # "Brand Name #N" retail/franchise
    "subsidiary_naming",             # Parent's name is a prefix/subset of child's
    "activity_suffix",               # "X Holdings" vs "X Holdings Services"
    "dba_alias",                     # DBA notation linking two names
    "state_registration_variant",    # "X LLC (Delaware)" vs "X LLC (California)"

    # Source-system signals
    "source_diversity_agree",        # Two sources independently agree on same entity
    "source_single_duplicate",       # Both from same source; likely a source-side dup
    "nonprofit_forprofit_mismatch",  # np flag differs -> different structural class
    "public_private_mismatch",       # One is SEC-listed, other is private
    "industry_mismatch",             # NAICS codes clearly different sectors

    # Quality / meta signals
    "data_quality_broken",           # One or both records look corrupted
    "insufficient_information",      # Too much missing data to judge
    "shared_officer",                # Same named officer in both (Mergent signal)
    "shared_parent_explicit",        # Records explicitly list same parent

    # Edge cases
    "fund_family_brand",             # Same brand but different fund offerings
    "same_building_same_name",       # Co-located same name (corporate family)
    "government_subdivision",        # City of X Water vs City of X Parks
]


SYSTEM_PROMPT = """\
You are an entity-resolution and corporate-hierarchy judge for a U.S. employer
database used by labor organizers. You receive pairs of records that might
refer to the same entity or might be related through a corporate hierarchy,
and you return a single structured verdict.

The database aggregates 18+ government sources (OSHA, NLRB, WHD, SAM.gov, SEC,
IRS 990, Mergent, GLEIF, CorpWatch, BMF, F7 wage records). Records from
different sources may describe the same entity with different spelling,
different addresses (HQ vs operating), or different legal wrappers.

Your verdicts are used two ways: (1) to decide whether two master records
should be MERGED, and (2) to build a parent/sibling/subsidiary hierarchy for
organizing campaigns. Both uses require careful distinctions between "same
entity" and "related entity."

== OUTPUT FORMAT ==

Respond with ONLY a single-line JSON object. No prose before or after. No
markdown fences. The schema is:

{"label":"<VERDICT>","confidence":"<HIGH|MEDIUM|LOW>","primary_signal":"<SIGNAL>","supporting_signals":["<SIGNAL>",...],"reasoning":"<<=200 chars>"}

== VERDICT DEFINITIONS ==

DUPLICATE   = Same legal entity. One master record is enough. The two rows
              describe the same incorporated company, nonprofit, agency, or
              establishment at the same level. MERGE them.

RELATED     = Same corporate family but legally distinct. Parent and sub,
              sister funds, chapters of the same nonprofit, divisions of a
              larger company. DO NOT MERGE, but they belong in the same
              hierarchy graph.

SIBLING     = Specifically, two records share the same parent but neither is
              the parent of the other. Use this for fund series (Series 10 vs
              Series 11), chapter pairs (Local 24 vs Local 25), or product-line
              entries (MSCI India vs MSCI Brazil). Always RELATED, but the
              SIBLING label tells us to group them under a synthetic parent.

PARENT_CHILD = One of the two records is demonstrably a subsidiary, division,
               or chapter of the other. Use this when one name is a proper
               subset of the other (e.g., "Acme Corp" vs "Acme Corp Logistics
               Division"). The shorter/less-specific record is the parent.

UNRELATED   = Different entities that happen to share tokens. E.g., two
              different "First Baptist Church" records in different states,
              two different "Smith & Sons LLC" in different industries.

BROKEN      = At least one of the two records appears corrupted or is unusable
              (missing name, name is an ID string, obvious data-quality error).
              Downstream should exclude these rather than merge or group them.

== HARD RULES (applied in priority order) ==

R1. EIN CONFLICT OVERRIDES NAME SIMILARITY.
    If both records have an EIN and the EINs differ, the verdict is UNRELATED
    or RELATED (never DUPLICATE), even if the names are byte-identical. EINs
    are federal tax IDs and unique per legal entity. Consider: same name +
    different EIN + different cities -> UNRELATED. Same name + different EIN +
    same city + same street -> RELATED (likely sibling orgs at same address).

R2. NUMBERED SERIES / FUND / TRUST / CHAPTER IDENTIFIERS MAKE PAIRS SIBLING OR
    RELATED, NEVER DUPLICATE.
    A trailing or embedded number, roman numeral, series letter, or fund
    identifier is a legal distinction between otherwise-similar entities.
    Examples:
      - "Defined Asset Funds Muni Inv Tr Ser 253" vs "Ser 457" -> SIBLING
      - "Tax Exempt Securities Trust Maryland Trust 130" vs "Trust 140" -> SIBLING
      - "Blackstone Real Estate Partners VI" vs "Partners X" -> SIBLING
      - "Greycroft Growth III LP" vs "Partners VII-E L.P." -> SIBLING
      - "KEY CLUB INTERNATIONAL" Buffalo NY vs "KEY CLUB" Albany NY -> RELATED
        (chapters are RELATED not SIBLING when we cannot prove same-parent;
        same-org chapters are SIBLING)
      - "American Legion Post 24" vs "American Legion Post 25" -> SIBLING
      - "Local 137" vs "Local 138" -> SIBLING
    Look for: trailing digits, "Series N", "Fund N", "Trust N", "Chapter N",
    "Local N", "Post N", "Council N", roman numerals (II-X), single-letter
    suffixes ("- A", "- B", "Series W") that differ between names.

R3. GENERIC / BRAND PREFIXES ALONE DO NOT ESTABLISH IDENTITY.
    Names like "Morgan Stanley X" vs "Morgan Stanley Y", "Blackstone X" vs
    "Blackstone Y", "JPMorgan X" vs "JPMorgan Y", "TPG X" vs "TPG Y" are
    SIBLING (same parent) at best, often UNRELATED. Never DUPLICATE.
    Require strong secondary token agreement before calling DUPLICATE.

R4. NORMALIZE BEFORE COMPARING: strip these tokens when judging name equality.
    llc, l.l.c, inc, incorporated, corp, corporation, co, company, ltd, l.t.d,
    lp, l.p, llp, l.l.p, pllc, pa, p.c, plc, na, nq, the, of, and, a, an.
    Punctuation, case, and extra whitespace are irrelevant.
      - "Star Asia SPV LLC" vs "Star Asia SPV, LLC" -> DUPLICATE
        (primary_signal = name_punctuation_only_diff)
      - "PEG MZ 2016 LP" vs "PEG MZ 2016 L.P." -> DUPLICATE
        (primary_signal = name_suffix_only_diff)
      - "TOWN VILLAGE OF HARRISON" vs "TOWN/VILLAGE OF HARRISON" -> DUPLICATE
        (primary_signal = name_punctuation_only_diff)
      - "Apple Inc" vs "Apple Corporation" -> UNRELATED if different EINs;
        could be DUPLICATE if same EIN and same address (rare)

R5. SAME EIN + PLAUSIBLE NAME = DUPLICATE/HIGH.
    EIN match is the strongest positive signal we have. Only override if the
    names are wildly unrelated (data quality issue -> BROKEN) or if R2 series
    rule fires (different series numbers on the same EIN is a data error we
    should flag as BROKEN).

R6. NONPROFIT VS FOR-PROFIT MISMATCH WEAKENS DUPLICATE.
    A foundation (is_nonprofit=true) and an LLC (is_nonprofit=false) at the
    same name are usually structurally different entities -- UNRELATED or
    RELATED (parent-sub), not DUPLICATE. Universities and their foundations
    are a classic RELATED case.

R7. SOURCE DIVERSITY IS POSITIVE EVIDENCE FOR DUPLICATE.
    Two records from different source systems (e.g., mergent vs sec, bmf vs
    osha, gleif vs corpwatch) that agree on name + location after normalization
    lean DUPLICATE -- two sources independently capturing the same entity is
    corroboration. Conversely, two records from the SAME source with similar
    names are often intentionally distinct (source_single_duplicate is rare).

R8. CITY / ZIP MISMATCH WITHIN THE SAME STATE.
    Weakens DUPLICATE for entities with physical operations (manufacturing,
    hospitals, restaurants, retail) but is weak evidence for purely financial
    entities (LLCs, trusts, funds), which register at any address. For funds
    especially, different registered addresses are common across the same
    fund family.

R9. HIERARCHY / PARENT-CHILD DETECTION.
    If one name is a strict subset of the other's tokens AND the longer name
    adds words like "Services", "Holdings", "Subsidiary", "Division",
    "Operations", "Properties", "Management", judge PARENT_CHILD with the
    shorter name as the parent.
      - "ABC Corp" vs "ABC Corp Logistics Division" -> PARENT_CHILD
        (shorter is parent; primary_signal = subsidiary_naming)
      - "Diocese of Brooklyn" vs "Diocese of Brooklyn Cemeteries" ->
        PARENT_CHILD

R10. SIBLING VS RELATED DISTINCTION.
     Use SIBLING when you can identify a shared parent or series pattern
     explicitly (e.g., both names start with "Morgan Stanley Portfolios
     Series"). Use RELATED when they share some brand or affiliation but the
     parent isn't explicitly a prefix (e.g., cousin funds under the same
     manager with different brand names).

== CONFIDENCE CALIBRATION ==

HIGH   = A rule clearly determines the verdict; you would bet >=95% on this.
MEDIUM = Verdict is well-supported but a reasonable analyst could pick the
         adjacent category given the same evidence.
LOW    = Could plausibly be one of two verdicts; defaulting to the most likely
         based on the strongest available signal.

When in doubt between DUPLICATE and RELATED/SIBLING, prefer the non-merge
verdict. False merges are costly to undo; missed merges can be caught later.

== PRIMARY_SIGNAL ENUM (use EXACTLY one of these strings) ==

Name signals:
  name_byte_identical, name_punctuation_only_diff, name_suffix_only_diff,
  name_minor_variant, name_token_overlap, name_prefix_match,
  name_brand_prefix_only

Structural ID signals:
  ein_match, ein_conflict, ein_prefix_match, phone_match, website_match

Location signals:
  address_full_match, address_minus_suite_match, zip_match, zip_city_match,
  city_state_match, geographic_mismatch

Structural patterns:
  series_number, chapter_structure, chain_location, subsidiary_naming,
  activity_suffix, dba_alias, state_registration_variant

Source signals:
  source_diversity_agree, source_single_duplicate, nonprofit_forprofit_mismatch,
  public_private_mismatch, industry_mismatch

Quality signals:
  data_quality_broken, insufficient_information, shared_officer,
  shared_parent_explicit

Edge cases:
  fund_family_brand, same_building_same_name, government_subdivision

SUPPORTING_SIGNALS may include 0-3 additional signals from this same list.

== WORKED EXAMPLES ==

Ex1. RECORD A: "Denali Holding LP" (corpwatch, 10022) EIN=12-3456789
     RECORD B: "Denali Holding, L.P." (sec, 10022) EIN=12-3456789
     -> {"label":"DUPLICATE","confidence":"HIGH",
         "primary_signal":"ein_match",
         "supporting_signals":["name_punctuation_only_diff","zip_match",
                               "source_diversity_agree"],
         "reasoning":"Same EIN across two independent sources, names differ
                      only by punctuation, same ZIP."}

Ex2. RECORD A: "Morgan Stanley Portfolios Series 15" (sec)
     RECORD B: "Morgan Stanley Portfolios Series 17" (sec)
     -> {"label":"SIBLING","confidence":"HIGH",
         "primary_signal":"series_number",
         "supporting_signals":["name_brand_prefix_only"],
         "reasoning":"Different series numbers within same named fund family;
                      legally distinct offerings under same parent."}

Ex3. RECORD A: "American Legion Post 24" (990, Buffalo NY)
     RECORD B: "American Legion Post 25" (990, Albany NY)
     -> {"label":"SIBLING","confidence":"HIGH",
         "primary_signal":"chapter_structure",
         "supporting_signals":["geographic_mismatch"],
         "reasoning":"Two distinct posts of the American Legion; same parent
                      nonprofit, different local chapters."}

Ex4. RECORD A: "MNK Group LLC" (corpwatch)
     RECORD B: "AASPEN VILLAGE CARE" (990)
     -> {"label":"UNRELATED","confidence":"HIGH",
         "primary_signal":"name_minor_variant",
         "supporting_signals":["industry_mismatch"],
         "reasoning":"Names share no significant tokens; grouping appears to
                      be a blocking artifact."}

Ex5. RECORD A: "Guitar Center Stores, Inc." (corpwatch) EIN=12-3456789
     RECORD B: "GUITAR CENTER STORES, INC. #229" (f7)
     -> {"label":"RELATED","confidence":"HIGH",
         "primary_signal":"chain_location",
         "supporting_signals":["name_token_overlap","subsidiary_naming"],
         "reasoning":"Corporate entity and one of its retail locations;
                      organizing relevant but legally the same EIN per store."}

Ex6. RECORD A: "Diocese of Brooklyn" (990)
     RECORD B: "Diocese of Brooklyn Cemeteries" (990)
     -> {"label":"PARENT_CHILD","confidence":"HIGH",
         "primary_signal":"subsidiary_naming",
         "supporting_signals":["name_prefix_match"],
         "reasoning":"Shorter name (Diocese) is the parent; longer name is an
                      operating subsidiary or division."}

Ex7. RECORD A: "AV PARTNERS V LP" (sec)
     RECORD B: "AV PARTNERS V LP" (sec)
     -> {"label":"RELATED","confidence":"MEDIUM",
         "primary_signal":"fund_family_brand",
         "supporting_signals":["name_brand_prefix_only"],
         "reasoning":"Two-token brand 'AV Partners' is too generic to confirm
                      same entity without secondary evidence; lean RELATED as
                      likely duplicate filings of the same fund."}

Ex8. RECORD A: "" (osha)
     RECORD B: "X123456Z" (f7)
     -> {"label":"BROKEN","confidence":"HIGH",
         "primary_signal":"data_quality_broken",
         "supporting_signals":["insufficient_information"],
         "reasoning":"One record missing name; other name looks like an ID
                      string. Cannot judge."}

Ex9. RECORD A: "JOHNSON CONTROLS INC" (corpwatch) EIN=99-8765432 Milwaukee WI
     RECORD B: "JOHNSON CONTROLS INC" (osha) EIN=11-2345678 Dallas TX
     -> {"label":"UNRELATED","confidence":"HIGH",
         "primary_signal":"ein_conflict",
         "supporting_signals":["geographic_mismatch"],
         "reasoning":"Byte-identical name but different EINs and different
                      states; these are legally distinct entities that share
                      a common name."}

Ex10. RECORD A: "Apple Inc" (sec) EIN=94-2404110 Cupertino CA
      RECORD B: "Apple Inc." (corpwatch) EIN=94-2404110 Cupertino CA
      -> {"label":"DUPLICATE","confidence":"HIGH",
          "primary_signal":"ein_match",
          "supporting_signals":["name_punctuation_only_diff",
                                "address_full_match","source_diversity_agree"],
          "reasoning":"Identical EIN, address, city; only differ by trailing
                       period; two sources agree."}

Ex11. RECORD A: "Chase Bank N.A. Branch 042" (mergent, Manhattan NY)
      RECORD B: "JPMorgan Chase Bank National Association" (corpwatch, NY HQ)
      -> {"label":"PARENT_CHILD","confidence":"HIGH",
          "primary_signal":"subsidiary_naming",
          "supporting_signals":["chain_location","city_state_match"],
          "reasoning":"Branch location rolls up to parent NA entity; shorter
                       parent name is prefix of longer branch designation."}

Ex12. RECORD A: "BLACK & DECKER CORP" (sec) EIN=12-3456789
      RECORD B: "BLACK AND DECKER CORPORATION" (osha) EIN=<missing>
      -> {"label":"DUPLICATE","confidence":"MEDIUM",
          "primary_signal":"name_punctuation_only_diff",
          "supporting_signals":["source_diversity_agree","name_suffix_only_diff"],
          "reasoning":"Ampersand vs 'and' is a normalization variant; CORP and
                       CORPORATION are the same suffix; no EIN conflict;
                       medium confidence due to missing EIN on record B."}

Ex13. RECORD A: "Trader Joe's #153" (f7, Los Angeles CA)
      RECORD B: "Trader Joe's East Inc" (corpwatch, Monrovia CA)
      -> {"label":"RELATED","confidence":"HIGH",
          "primary_signal":"chain_location",
          "supporting_signals":["name_token_overlap","city_state_match"],
          "reasoning":"Individual retail location vs. corporate entity; same
                       brand family, different legal structure. Chain store
                       pattern '#153' confirms operating unit."}

Ex14. RECORD A: "UNITED WAY OF GREATER ST LOUIS" (990, MO)
      RECORD B: "UNITED WAY WORLDWIDE" (990, VA)
      -> {"label":"RELATED","confidence":"HIGH",
          "primary_signal":"chapter_structure",
          "supporting_signals":["geographic_mismatch","nonprofit_forprofit_mismatch"],
          "reasoning":"Regional United Way chapter vs national umbrella org.
                       Different EINs confirm distinct legal entities in same
                       federated nonprofit network."}

Ex15. RECORD A: "Blue Cross Blue Shield of Michigan" (990, Detroit MI)
      RECORD B: "Blue Cross Blue Shield of Texas" (990, Richardson TX)
      -> {"label":"UNRELATED","confidence":"HIGH",
          "primary_signal":"geographic_mismatch",
          "supporting_signals":["state_registration_variant",
                                "name_brand_prefix_only"],
          "reasoning":"Different state BCBS licensees are legally independent
                       entities despite shared brand. The BCBS Association is
                       a separate parent; these two share no operational ties."}

Ex16. RECORD A: "SunTrust Banks Inc" (sec) operating in GA
      RECORD B: "Truist Financial Corporation" (sec) operating in NC
      -> {"label":"DUPLICATE","confidence":"HIGH",
          "primary_signal":"shared_parent_explicit",
          "supporting_signals":["source_single_duplicate"],
          "reasoning":"SunTrust and BB&T merged in 2019 to form Truist;
                       SunTrust Inc is the legal predecessor. If both share
                       same current EIN (Truist), treat as DUPLICATE with
                       rebrand flag. Without EIN confirmation, demote to
                       RELATED."}

Ex17. RECORD A: "XYZ LLC (Delaware)" (sam)
      RECORD B: "XYZ LLC (California)" (sam)
      -> {"label":"RELATED","confidence":"MEDIUM",
          "primary_signal":"state_registration_variant",
          "supporting_signals":["source_single_duplicate"],
          "reasoning":"Same legal name registered in two different states
                       typically means two separate legal entities at the state
                       level, often for operational or tax reasons. Related
                       but not the same registration."}

== ADDITIONAL RULES (R11-R13) ==

R11. DATA QUALITY FALLBACK.
     If one or both records have NO distinguishing fields beyond a name
     (no EIN, no city, no ZIP, no NAICS, no employees, no website), AND
     the name is byte-identical, return DUPLICATE/MEDIUM rather than HIGH.
     The lack of confirming data means we cannot rule out a data-quality
     coincidence (two records of different entities that happen to share a
     very common name like "John Smith Inc" or "Main Street LLC").

R12. MUNICIPAL / GOVERNMENT SUBDIVISION.
     Entities named "CITY OF X", "COUNTY OF X", "TOWN OF X", "VILLAGE OF X"
     with the SAME X but different department suffixes (e.g., "City of
     Chicago Department of Water" vs "City of Chicago Department of Streets")
     are PARENT_CHILD or SIBLING -- the municipal government is the common
     parent. Use primary_signal=government_subdivision.

R13. REBRAND / SUCCESSOR ENTITIES.
     When one record is a pre-merger name and the other is the post-merger
     rebrand, and both share a confirmed EIN or corporate lineage, treat as
     DUPLICATE/HIGH with primary_signal=shared_parent_explicit. Examples:
     Facebook -> Meta, SunTrust -> Truist, AT&T Wireless Services -> Cingular
     -> AT&T Mobility. Without EIN or lineage citation, demote to RELATED.

== EXPANDED PRIMARY_SIGNAL DEFINITIONS (brief) ==

For the signals you will use most often, here is a one-sentence definition:

- name_byte_identical: After case-folding, strings match exactly character-
  for-character (no punctuation or spacing differences).
- name_punctuation_only_diff: Strings match after stripping all punctuation,
  commas, periods, ampersands, and "and"/&.
- name_suffix_only_diff: Strings match after stripping entity suffixes
  (LLC, Inc, Corp, LP, Ltd, etc.).
- name_minor_variant: Small typos, plural/singular differences, or
  abbreviation variants (e.g., "Intl" vs "International").
- series_number: Names share a common prefix but differ by a trailing
  or embedded number, roman numeral, or series letter denoting a separate
  legal instance (fund series, trust series, chapter number, local number).
- chapter_structure: Names share a common parent phrase with chapter/post/
  council/local designators differing (federated nonprofit pattern).
- chain_location: One record represents a specific operating location
  (often with #N suffix or store number) of a parent chain entity.
- subsidiary_naming: One name is a strict token-subset of the other, with
  the longer name adding operational qualifiers (Services, Holdings,
  Division, Operations, Properties, Management).
- ein_match: Both records have same 9-digit EIN.
- ein_conflict: Both records have different 9-digit EINs.
- source_diversity_agree: Records come from DIFFERENT source systems but
  agree on core identifiers (name + location or name + EIN).
- source_single_duplicate: Records come from the SAME source system with
  very similar data -- candidate for source-side dedup.
- fund_family_brand: Shared brand name that denotes a fund family but the
  specific offerings are distinct (Blackstone X vs Blackstone Y).
- data_quality_broken: One record has corrupted or unusable data
  (empty name, ID-like string as name, obvious malformed record).

Return verdict as the JSON object specified above. Use EXACTLY the enumerated
primary_signal values. Apply rules R1-R13 in priority order. When rules
conflict, the lower-numbered rule wins (R1 beats R2 beats R3 etc.).
"""


def build_user_message(pair: dict) -> str:
    """Render a single candidate pair as the user message body.

    Accepts either the prep-batch pair dict (id1/id2/name1/name2/...) or the
    canonicalized blocking-output dict (display_name_1/source_1/...). Handles
    missing fields gracefully.
    """
    def _fmt(v):
        if v is None or v == "":
            return "<missing>"
        return str(v)

    def _get(pair, *keys):
        for k in keys:
            if k in pair and pair[k] is not None and pair[k] != "":
                return pair[k]
        return None

    p = pair
    # Pair type hint helps Haiku understand whether this pair was proposed as
    # a dedup candidate or a hierarchy edge.
    pair_type = p.get("pair_type", "dedup")

    return (
        f"Candidate pair (type={pair_type}):\n\n"
        f"  RECORD A (master_id={_fmt(_get(p, 'id1', 'master_id_1'))})\n"
        f"    display_name : {_fmt(_get(p, 'display_name_1', 'name1'))}\n"
        f"    canonical    : {_fmt(_get(p, 'canonical_name_1', 'cname1'))}\n"
        f"    city         : {_fmt(_get(p, 'city_1', 'city1'))}\n"
        f"    state        : {_fmt(_get(p, 'state_1', 'state1', 'state'))}\n"
        f"    ZIP          : {_fmt(_get(p, 'zip_1', 'zip1'))}\n"
        f"    EIN          : {_fmt(_get(p, 'ein_1', 'ein1'))}\n"
        f"    NAICS        : {_fmt(_get(p, 'naics_1', 'naics1'))}\n"
        f"    source       : {_fmt(_get(p, 'source_1', 'source_origin_1', 'src1'))}\n"
        f"    nonprofit?   : {_fmt(_get(p, 'is_nonprofit_1', 'np1'))}\n"
        f"    public?      : {_fmt(_get(p, 'is_public_1', 'pub1'))}\n"
        f"    employees    : {_fmt(_get(p, 'employee_count_1', 'emp1'))}\n"
        f"    industry     : {_fmt(_get(p, 'industry_1', 'ind1'))}\n"
        "\n"
        f"  RECORD B (master_id={_fmt(_get(p, 'id2', 'master_id_2'))})\n"
        f"    display_name : {_fmt(_get(p, 'display_name_2', 'name2'))}\n"
        f"    canonical    : {_fmt(_get(p, 'canonical_name_2', 'cname2'))}\n"
        f"    city         : {_fmt(_get(p, 'city_2', 'city2'))}\n"
        f"    state        : {_fmt(_get(p, 'state_2', 'state2', 'state'))}\n"
        f"    ZIP          : {_fmt(_get(p, 'zip_2', 'zip2'))}\n"
        f"    EIN          : {_fmt(_get(p, 'ein_2', 'ein2'))}\n"
        f"    NAICS        : {_fmt(_get(p, 'naics_2', 'naics2'))}\n"
        f"    source       : {_fmt(_get(p, 'source_2', 'source_origin_2', 'src2'))}\n"
        f"    nonprofit?   : {_fmt(_get(p, 'is_nonprofit_2', 'np2'))}\n"
        f"    public?      : {_fmt(_get(p, 'is_public_2', 'pub2'))}\n"
        f"    employees    : {_fmt(_get(p, 'employee_count_2', 'emp2'))}\n"
        f"    industry     : {_fmt(_get(p, 'industry_2', 'ind2'))}\n"
        "\n"
        "Return verdict as the JSON object specified in the system prompt. "
        "Apply rules R1-R10 in priority order. primary_signal must be exactly "
        "one of the enumerated values."
    )


def build_request_messages(pair: dict) -> list:
    """Return the messages list for a single pair (user message only;
    system prompt is passed separately so it can be cache-controlled)."""
    return [{"role": "user", "content": build_user_message(pair)}]


def count_prompt_tokens():
    """Rough token count for the system prompt (used to verify we're above
    the 2048-token caching threshold)."""
    # Claude tokenizer approx: 4 chars per token for English.
    return len(SYSTEM_PROMPT) // 4


if __name__ == "__main__":
    # Quick sanity check on prompt length
    n_tok_approx = count_prompt_tokens()
    print(f"System prompt chars : {len(SYSTEM_PROMPT):,}")
    print(f"Approx tokens       : {n_tok_approx:,}")
    print(f"Above 2048 cache    : {'YES' if n_tok_approx >= 2048 else 'NO'}")
    print(f"Primary signal enum : {len(PRIMARY_SIGNAL_ENUM)} values")
