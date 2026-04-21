"""
Shared prompt construction for the Claude-as-judge dedup task.

Used by both the live-API calibration script and the Batch API submitter so
the exact same prompt is evaluated in both modes. The system prompt is marked
for prompt caching -- it's identical across every request, so the input cost
collapses to the cache-read price after the first hit.
"""

# Bumped on every prompt revision so we can attribute results to a version.
PROMPT_VERSION = "v1.0"

JUDGE_MODEL = "claude-haiku-4-5-20251001"
MAX_OUTPUT_TOKENS = 250

SYSTEM_PROMPT = """\
You are an entity-resolution judge for a U.S. employer database. You receive a
pair of records that *might* refer to the same legal entity. You return a
single verdict.

== Output format ==
Respond with ONLY a single-line JSON object, no prose, no markdown fences:
{"verdict":"DUPLICATE|RELATED|DIFFERENT","confidence":"HIGH|MEDIUM|LOW","reason":"<<=200 chars"}

== Verdict definitions ==
- DUPLICATE  = same legal entity. Should be merged into one master record.
- RELATED    = same parent company / fund family / corporate group, but legally
               distinct entities (e.g., parent + subsidiary, sister funds, two
               local chapters of the same nonprofit). Should NOT be merged.
- DIFFERENT  = unrelated entities that happen to share words.

== HARD RULES ==

R1. **EIN conflict overrides name similarity.** If both records have an EIN and
    the EINs differ, the verdict is DIFFERENT or RELATED (never DUPLICATE),
    even if the names are byte-identical. EINs are federal tax IDs and unique
    per legal entity.

R2. **Numbered series / fund / trust / chapter identifiers make pairs DIFFERENT
    or RELATED, never DUPLICATE.** A trailing or embedded number, roman numeral,
    series letter, or fund identifier is a legal distinction:
      - "Defined Asset Funds Municipal Inv Tr Fd Ser 253" vs "Ser 457" -> RELATED
      - "Tax Exempt Securities Trust Maryland Trust 130" vs "Maryland Trust 140" -> RELATED
      - "Blackstone Real Estate Partners VI" vs "Blackstone Real Estate Partners X" -> RELATED
      - "Greycroft Growth III LP" vs "Greycroft Partners VII-E L.P." -> RELATED
      - "KEY CLUB INTERNATIONAL" Buffalo NY vs "KEY CLUB INTERNATIONAL" Albany NY -> RELATED (chapters)
    Look for: trailing digits, "Series N", "Fund N", "Trust N", "Chapter N",
    "Local N", roman numerals (II, III, IV, V, VI, VII, VIII, IX, X), or
    single-letter suffixes ("- A", "- B", "Series W") that differ between names.

R3. **Generic/brand prefixes alone do not establish identity.** Names like
    "Morgan Stanley X" vs "Morgan Stanley Y", "Blackstone X" vs "Blackstone Y",
    "JPMorgan X" vs "JPMorgan Y" are RELATED (same parent) at best, often
    DIFFERENT. Require strong secondary token agreement before calling DUPLICATE.

R4. **Strip these tokens before comparing core names**: llc, l.l.c, inc, corp,
    corporation, co, ltd, l.t.d, lp, l.p, llp, l.l.p, pllc, pa, p.c, plc, na,
    nq, the, of, and, a, an. Punctuation is also irrelevant.
      - "Star Asia SPV LLC" vs "Star Asia SPV, LLC" -> DUPLICATE
      - "PEG MZ 2016 LP" vs "PEG MZ 2016 L.P." -> DUPLICATE
      - "TOWN VILLAGE OF HARRISON" vs "TOWN/VILLAGE OF HARRISON" -> DUPLICATE

R5. **Same EIN + plausible name = DUPLICATE/HIGH.** EIN match is the strongest
    positive signal. Only override if the names are wildly unrelated (data
    quality issue) or if R2 series rule fires.

R6. **Nonprofit vs for-profit mismatch** weakens DUPLICATE.  A foundation
    (np=true) and an LLC (np=false) at the same name are usually two
    structurally different entities -- DIFFERENT or RELATED, not DUPLICATE.

R7. **Source diversity is positive evidence.** If the two records come from
    different source systems (e.g., bmf vs sec, mergent vs osha) and the names
    + location agree after normalization, lean DUPLICATE. Two sources
    independently capturing the same entity is corroboration.

R8. **City/ZIP mismatch within the same state** weakens DUPLICATE for entities
    with physical operations (manufacturing, hospitals, restaurants) but is
    weak evidence for purely financial entities (LLCs, trusts, funds), which
    can register at any address.

== Confidence calibration ==
HIGH   = Rules clearly determine the verdict; would bet 95%+ on this.
MEDIUM = Verdict is well-supported but a reasonable analyst could pick the
         adjacent category given the same evidence.
LOW    = Could plausibly be any of two verdicts; defaulting based on the
         strongest available signal.

When in doubt between DUPLICATE and RELATED, prefer RELATED. False merges are
costly to undo; missed merges can be caught later.
"""


def build_user_message(pair: dict) -> str:
    """Render a single candidate pair as the user message body."""
    def _fmt(v):
        if v is None or v == "":
            return "<missing>"
        return str(v)

    p = pair
    return (
        "Candidate pair:\n"
        f"  RECORD A (master_id={_fmt(p.get('id1'))})\n"
        f"    display_name : {_fmt(p.get('display_name_1') or p.get('name1'))}\n"
        f"    canonical    : {_fmt(p.get('canonical_name_1') or p.get('cname1'))}\n"
        f"    city/state/zip: {_fmt(p.get('city_1') or p.get('city1'))} / NY / {_fmt(p.get('zip_1') or p.get('zip1'))}\n"
        f"    EIN          : {_fmt(p.get('ein_1') or p.get('ein1'))}\n"
        f"    NAICS        : {_fmt(p.get('naics_1') or p.get('naics1'))}\n"
        f"    source       : {_fmt(p.get('source_1') or p.get('src1'))}\n"
        f"    nonprofit?   : {_fmt(p.get('is_nonprofit_1') if 'is_nonprofit_1' in p else p.get('np1'))}\n"
        f"    public?      : {_fmt(p.get('is_public_1') if 'is_public_1' in p else p.get('pub1'))}\n"
        f"    employees    : {_fmt(p.get('employee_count_1') or p.get('emp1'))}\n"
        f"    industry     : {_fmt(p.get('industry_1') or p.get('ind1'))}\n"
        "\n"
        f"  RECORD B (master_id={_fmt(p.get('id2'))})\n"
        f"    display_name : {_fmt(p.get('display_name_2') or p.get('name2'))}\n"
        f"    canonical    : {_fmt(p.get('canonical_name_2') or p.get('cname2'))}\n"
        f"    city/state/zip: {_fmt(p.get('city_2') or p.get('city2'))} / NY / {_fmt(p.get('zip_2') or p.get('zip2'))}\n"
        f"    EIN          : {_fmt(p.get('ein_2') or p.get('ein2'))}\n"
        f"    NAICS        : {_fmt(p.get('naics_2') or p.get('naics2'))}\n"
        f"    source       : {_fmt(p.get('source_2') or p.get('src2'))}\n"
        f"    nonprofit?   : {_fmt(p.get('is_nonprofit_2') if 'is_nonprofit_2' in p else p.get('np2'))}\n"
        f"    public?      : {_fmt(p.get('is_public_2') if 'is_public_2' in p else p.get('pub2'))}\n"
        f"    employees    : {_fmt(p.get('employee_count_2') or p.get('emp2'))}\n"
        f"    industry     : {_fmt(p.get('industry_2') or p.get('ind2'))}\n"
        "\n"
        "Return verdict as the JSON object specified in the system prompt. Apply rules R1-R8."
    )


def build_request_messages(pair: dict) -> list:
    """Return the messages list for a single pair (user message only;
    system prompt is passed separately so it can be cache-controlled)."""
    return [{"role": "user", "content": build_user_message(pair)}]
