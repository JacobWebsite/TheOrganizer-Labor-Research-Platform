"""
Validate candidate heuristic rules H1-H5 against the 31,532 LLM-labeled
pairs from the 2026-04-16 batch. For each rule, compute:
  - Fires: how many pairs does the rule flag?
  - Precision vs DUPLICATE: of those, what fraction are LLM=DUPLICATE?
  - Precision vs not-DUPLICATE (for H4): what fraction are NOT LLM=DUPLICATE?
  - Recall of LLM DUPLICATEs: what fraction of all 258 LLM-DUPs does the rule catch?

Also tests a combined gate: (H1 OR H2 OR H3) AND NOT H4 as an enhanced
auto_duplicate classifier that could pre-empt the LLM on future runs.

No API calls. Pure Python on existing CSV + JSON. Output: console summary
plus `rule_validation_report.json`.
"""
import csv
import json
import os
import re
from collections import Counter

DIR = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = os.path.join(DIR, 'candidates_singletons_scored.json')
RESULTS_CSV = os.path.join(DIR, 'anthropic_batch_results.csv')
OUT_JSON = os.path.join(DIR, 'rule_validation_report.json')


# ---------------------------------------------------------------------------
# Normalizers (variants of increasing aggressiveness)
# ---------------------------------------------------------------------------

LEGAL_SUFFIX_RE = re.compile(
    r'\b('
    r'llc|l\.l\.c|inc|incorporated|corp|corporation|company|co|ltd|limited|'
    r'lp|l\.p|llp|l\.l\.p|pc|p\.c|pllc|pa|p\.a|na|n\.a|sa|s\.a|'
    r'gmbh|plc|ag|bv|nv|se|srl|sarl|'
    r'the|of|and|an|a|nq'
    r')\b',
    re.IGNORECASE,
)

PUNCT_RE = re.compile(r'[^\w\s]')  # keep letters, digits, underscore, whitespace
MULTISPACE_RE = re.compile(r'\s+')


def normalize_punct_only(name):
    if not name:
        return ''
    n = name.lower()
    n = PUNCT_RE.sub(' ', n)
    n = MULTISPACE_RE.sub(' ', n).strip()
    return n


def normalize_all(name):
    """Strip punctuation + ALL legal suffixes + collapse whitespace."""
    if not name:
        return ''
    n = name.lower()
    n = PUNCT_RE.sub(' ', n)
    n = LEGAL_SUFFIX_RE.sub(' ', n)
    n = MULTISPACE_RE.sub(' ', n).strip()
    return n


# ---------------------------------------------------------------------------
# H4: series-number detection
# ---------------------------------------------------------------------------

ROMAN = r'(?:i{1,3}|iv|v|vi{0,3}|ix|x{1,3}|xi{0,3}|xiv|xv|xvi{0,3}|xix|xx)'
TRAILING_TOKEN = re.compile(
    rf'\s+(?:'
    rf'\d+'                             # trailing integer
    rf'|{ROMAN}'                        # roman numeral
    rf'|series\s*[a-z0-9]+'             # "series 5" / "series A"
    rf'|ser\s*[a-z0-9]+'                # "ser 253"
    rf'|fund\s*[a-z0-9]+'               # "fund II"
    rf'|trust\s*[a-z0-9]+'              # "trust 130"
    rf'|chapter\s*[a-z0-9]+'            # "chapter 42"
    rf'|local\s*\d+'                    # "local 51"
    rf'|[a-z]'                          # trailing single letter "- A"
    rf')$',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# H5-H8 additional rule helpers
# ---------------------------------------------------------------------------

PAREN_RE = re.compile(r'\s*[\(\[\{][^\)\]\}]*[\)\]\}]\s*')
AT_SUFFIX_RE = re.compile(r'\s*@\s+.+$', re.IGNORECASE)   # " @ WYSP-FM..."
DBA_RE = re.compile(r'\s+d[\./]?b[\./]?a\s+.+$', re.IGNORECASE)  # " d/b/a ..." / " dba ..."
SLASH_SUFFIX_RE = re.compile(r'\s+/\s+.+$')  # " / KWM..."
COMMA_SECOND_CLAUSE_RE = re.compile(r',\s+(?!(?:llc|l\.l\.c|inc|corp|ltd|lp|co|pllc|pc|pa)\b).+$', re.IGNORECASE)

ABBREV = {
    'hosp': 'hospital', 'ctr': 'center', 'cntrl': 'central', 'cntr': 'center',
    'assn': 'association', 'dept': 'department', 'natl': 'national',
    'govt': 'government', 'mfg': 'manufacturing', 'mgmt': 'management',
    'sys': 'systems', 'svcs': 'services', 'svc': 'service',
    'intl': 'international', 'univ': 'university', 'inst': 'institute',
    'bldg': 'building', 'constr': 'construction', 'dev': 'development',
    'dist': 'distribution', 'environ': 'environmental', 'equip': 'equipment',
    'engr': 'engineering', 'eng': 'engineering', 'maint': 'maintenance',
    'amer': 'american', 'med': 'medical',
}


def strip_decorations(name):
    """Strip parenthetical content, @-suffix, d/b/a clause, slash-suffix,
    and comma-introduced secondary clauses (that aren't legal suffixes)."""
    if not name:
        return ''
    n = name
    n = DBA_RE.sub('', n)
    n = SLASH_SUFFIX_RE.sub('', n)
    n = AT_SUFFIX_RE.sub('', n)
    n = PAREN_RE.sub(' ', n)
    n = COMMA_SECOND_CLAUSE_RE.sub('', n)
    return n


def expand_abbrevs(tokens):
    return [ABBREV.get(t, t) for t in tokens]


def normalize_h5(name):
    """Decorations stripped, then H2-style normalization."""
    return normalize_all(strip_decorations(name))


def normalize_h6(name):
    """H2 normalization, then remove ALL whitespace (handles 'Sport BLX' vs 'SportBLX')."""
    return re.sub(r'\s+', '', normalize_all(name))


def normalize_h8(name):
    """H2 + abbreviation expansion."""
    n = normalize_all(strip_decorations(name))
    tokens = n.split()
    tokens = expand_abbrevs(tokens)
    return ' '.join(tokens)


def h5_parenthetical_strip(pair):
    n1 = normalize_h5(pair.get('canonical_name_1') or pair.get('display_name_1'))
    n2 = normalize_h5(pair.get('canonical_name_2') or pair.get('display_name_2'))
    if not n1 or not n2:
        return False
    # Require non-trivial result; must be meaningfully long to avoid "inc"=="inc" fires
    if len(n1) < 5 or len(n2) < 5:
        return False
    return n1 == n2


def h6_space_collapse(pair):
    n1 = normalize_h6(pair.get('canonical_name_1') or pair.get('display_name_1'))
    n2 = normalize_h6(pair.get('canonical_name_2') or pair.get('display_name_2'))
    if not n1 or not n2:
        return False
    if len(n1) < 6 or len(n2) < 6:
        return False
    # Must also come from same ZIP to avoid coincidence
    if pair['scores'].get('zip5_match', 0) < 1.0:
        return False
    return n1 == n2


def h7_dba_strip(pair):
    """Fires only if one side has d/b/a clause and stripping it yields the other side."""
    raw1 = pair.get('canonical_name_1') or pair.get('display_name_1') or ''
    raw2 = pair.get('canonical_name_2') or pair.get('display_name_2') or ''
    has_dba1 = bool(DBA_RE.search(raw1))
    has_dba2 = bool(DBA_RE.search(raw2))
    if not (has_dba1 or has_dba2):
        return False
    n1 = normalize_all(DBA_RE.sub('', raw1))
    n2 = normalize_all(DBA_RE.sub('', raw2))
    if not n1 or not n2 or len(n1) < 4:
        return False
    return n1 == n2


def h8_abbrev_expansion(pair):
    n1 = normalize_h8(pair.get('canonical_name_1') or pair.get('display_name_1'))
    n2 = normalize_h8(pair.get('canonical_name_2') or pair.get('display_name_2'))
    if not n1 or not n2:
        return False
    if len(n1) < 5 or len(n2) < 5:
        return False
    return n1 == n2


def h9_token_containment(pair):
    """Shorter name's tokens all appear in longer name's tokens, AND same ZIP.
    Catches subsidiary/division patterns like 'CBS BROADCASTING INC' inside
    'CBS BROADCASTING INC. (WBBM-TV)'."""
    # Same ZIP required to avoid franchise false positives
    if pair['scores'].get('zip5_match', 0) < 1.0:
        return False
    n1 = normalize_h8(pair.get('canonical_name_1') or pair.get('display_name_1'))
    n2 = normalize_h8(pair.get('canonical_name_2') or pair.get('display_name_2'))
    if not n1 or not n2:
        return False
    t1 = set(n1.split())
    t2 = set(n2.split())
    if len(t1) < 2 or len(t2) < 2:
        return False
    # Shorter's tokens fully contained in longer's
    shorter, longer = (t1, t2) if len(t1) <= len(t2) else (t2, t1)
    if not shorter.issubset(longer):
        return False
    # Must be meaningful overlap: shorter side has 2+ non-trivial tokens
    # AND overlap is >= 2 tokens (not just "the" or "inc")
    if len(shorter) < 2:
        return False
    # Additional check: the non-overlapping tokens in longer side shouldn't
    # include a series-number indicator (already caught by H4 but belt+suspenders)
    extra = longer - shorter
    for tok in extra:
        if tok.isdigit() or re.fullmatch(r'(?:' + ROMAN + ')', tok):
            return False
    return True


def h10_sparse_whitespace(pair):
    """Names differ only by extra/missing whitespace AND same ZIP.
    Catches 'Sport BLX' vs 'SportBLX', '  Eurest' vs 'Eurest'."""
    raw1 = pair.get('canonical_name_1') or pair.get('display_name_1') or ''
    raw2 = pair.get('canonical_name_2') or pair.get('display_name_2') or ''
    # Collapse internal whitespace entirely
    c1 = re.sub(r'\s+', '', raw1.lower())
    c2 = re.sub(r'\s+', '', raw2.lower())
    if c1 != c2:
        return False
    # But originals must actually differ (otherwise it's the trivial match)
    return raw1.strip().lower() != raw2.strip().lower()


# Stop-words ignored when building acronyms (typical English articles/conjunctions)
ACRONYM_STOPWORDS = {'the', 'of', 'and', 'a', 'an', 'in', 'for', 'at', 'by', 'to',
                     'or', 'on', 'with', 'as', 'llc', 'inc', 'corp', 'ltd', 'lp',
                     'llp', 'co', 'pc', 'pa', 'pllc'}


def _build_acronym(text):
    """Letters from first char of each non-stopword token."""
    tokens = re.sub(r'[^\w\s]', ' ', text.lower()).split()
    return ''.join(t[0] for t in tokens if t and t not in ACRONYM_STOPWORDS and t[0].isalpha())


def h11_acronym_match(pair):
    """One side looks like an acronym/abbreviation of the other AND same ZIP.
    Catches 'BASICS' inside 'Bronx Addiction Services Integrated Concepts System'.
    Also catches parenthetical acronyms like 'Bronx Addiction Services (BASICS)'.
    Uses display_name (not canonical_name) because canonical strips parens."""
    if pair['scores'].get('zip5_match', 0) < 1.0:
        return False
    # display_name preserves parens; canonical has them stripped to spaces
    raw1 = pair.get('display_name_1') or pair.get('canonical_name_1') or ''
    raw2 = pair.get('display_name_2') or pair.get('canonical_name_2') or ''

    # Consider both raw sides and their paren-extracted tokens (for "FOO (ACME)" pattern)
    def candidates(raw):
        out = {normalize_punct_only(raw)}
        for m in re.findall(r'\(([^)]+)\)', raw):
            out.add(normalize_punct_only(m))
        return out

    c1 = candidates(raw1)
    c2 = candidates(raw2)

    # Long-form acronyms: for each combination, check if one is an acronym of the other
    for a in c1:
        for b in c2:
            if not a or not b:
                continue
            # a looks like an acronym if it's a single token, 3-8 letters, all alpha
            short, long_ = (a, b) if len(a) < len(b) else (b, a)
            if len(short.split()) != 1 or not short.isalpha() or not (3 <= len(short) <= 10):
                continue
            if len(long_.split()) < 3:
                continue
            acr = _build_acronym(long_)
            if acr.lower() == short.lower():
                return True
    return False


# Activity/descriptor suffix tokens that describe WHAT a company does
# rather than WHICH entity it is. Extra-token differences in these words
# (while shorter name is a prefix) suggest a division/subsidiary, not a
# distinct entity — LLM often flags these as DUPLICATE not RELATED because
# they share EIN/address. Use as an additional positive signal, not a demoter.
ACTIVITY_TOKENS = {
    'production', 'packing', 'packaging', 'services', 'service', 'operations',
    'management', 'distribution', 'logistics', 'solutions', 'systems',
    'technologies', 'manufacturing', 'sales', 'marketing', 'consulting',
    'development', 'holdings', 'enterprises', 'partners', 'group',
    'international', 'inc', 'corp', 'corporation', 'llc', 'ltd', 'co',
    'limited', 'incorporated',
}


def h12_activity_suffix_prefix(pair):
    """Shorter name is prefix of longer name AND extra tokens are all
    activity/descriptor words AND same ZIP. Catches 'Bland Farms' ⊂
    'Bland Farms Production and Packing' = likely same company."""
    if pair['scores'].get('zip5_match', 0) < 1.0:
        return False
    n1 = normalize_punct_only(pair.get('canonical_name_1') or pair.get('display_name_1'))
    n2 = normalize_punct_only(pair.get('canonical_name_2') or pair.get('display_name_2'))
    if not n1 or not n2 or n1 == n2:
        return False
    t1 = n1.split()
    t2 = n2.split()
    shorter, longer = (t1, t2) if len(t1) <= len(t2) else (t2, t1)
    # Shorter must have >= 2 meaningful tokens
    if len(shorter) < 2 or len(longer) <= len(shorter):
        return False
    # Shorter tokens must be exact prefix of longer tokens
    if longer[:len(shorter)] != shorter:
        return False
    # Extra tokens in longer side must ALL be activity descriptors
    extra = longer[len(shorter):]
    if not extra:
        return False
    if not all(t in ACTIVITY_TOKENS or t in {'and', 'of', 'the', 'for'} for t in extra):
        return False
    return True


def h4_series_difference(name1, name2):
    """Return True if names differ ONLY in a trailing series/numeric identifier."""
    n1 = normalize_punct_only(name1)
    n2 = normalize_punct_only(name2)
    # Strip trailing identifier from each
    n1_stripped = TRAILING_TOKEN.sub('', n1).strip()
    n2_stripped = TRAILING_TOKEN.sub('', n2).strip()
    if not n1_stripped or not n2_stripped:
        return False
    # Must be non-trivial remaining core (avoid false fires on very short names)
    if len(n1_stripped) < 8:
        return False
    # Cores identical, but originals differ
    return n1_stripped == n2_stripped and n1 != n2


# ---------------------------------------------------------------------------
# Individual rule evaluators
# ---------------------------------------------------------------------------

def h1_punct_invariant(pair):
    """Names identical after punctuation strip."""
    n1 = normalize_punct_only(pair.get('canonical_name_1') or pair.get('display_name_1'))
    n2 = normalize_punct_only(pair.get('canonical_name_2') or pair.get('display_name_2'))
    return bool(n1) and n1 == n2


def h2_legal_form_agnostic(pair):
    """Names identical after punctuation + legal-suffix strip."""
    n1 = normalize_all(pair.get('canonical_name_1') or pair.get('display_name_1'))
    n2 = normalize_all(pair.get('canonical_name_2') or pair.get('display_name_2'))
    if not n1 or not n2:
        return False
    # Require minimum length to avoid stripping everything
    return n1 == n2 and len(n1) >= 4


def h3_cross_source_zip_name(pair):
    """Different sources + high name similarity + same ZIP5."""
    s1 = (pair.get('source_1') or '').strip()
    s2 = (pair.get('source_2') or '').strip()
    if not s1 or not s2 or s1 == s2:
        return False
    if pair['scores'].get('zip5_match', 0) < 1.0:
        return False
    # High name similarity -- use max of standard/aggressive to be generous
    name_sim = max(pair['scores'].get('name_standard_sim', 0),
                   pair['scores'].get('name_aggressive_sim', 0))
    return name_sim >= 0.85


def h4_series_rule(pair):
    """Fires as anti-duplicate: trailing series differs."""
    return h4_series_difference(
        pair.get('canonical_name_1') or pair.get('display_name_1'),
        pair.get('canonical_name_2') or pair.get('display_name_2'),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Load LLM verdicts keyed by (id1, id2)
    verdicts = {}
    with open(RESULTS_CSV, 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            key = (int(r['id1']), int(r['id2'])) if r['id1'] and r['id2'] else None
            if key:
                verdicts[key] = {
                    'verdict': r['verdict'],
                    'confidence': r['confidence'],
                    'classification': r['classification'],
                }

    # Load pair details
    with open(CANDIDATES, 'r', encoding='utf-8') as f:
        pairs = json.load(f)

    print(f'Loaded {len(pairs):,} pairs, {len(verdicts):,} LLM verdicts.')
    total_dup = sum(1 for v in verdicts.values() if v['verdict'] == 'DUPLICATE')
    total_rel = sum(1 for v in verdicts.values() if v['verdict'] == 'RELATED')
    total_diff = sum(1 for v in verdicts.values() if v['verdict'] == 'DIFFERENT')
    print(f'LLM verdicts: DUPLICATE={total_dup:,}  RELATED={total_rel:,}  DIFFERENT={total_diff:,}')

    rules = [
        ('H1_punct_invariant',  h1_punct_invariant,  'DUPLICATE'),
        ('H2_legal_form_agnostic', h2_legal_form_agnostic, 'DUPLICATE'),
        ('H3_cross_src_zip_name', h3_cross_source_zip_name, 'DUPLICATE'),
        ('H4_series_anti_dup',  h4_series_rule, 'NOT_DUPLICATE'),
        ('H5_decorations_strip',  h5_parenthetical_strip, 'DUPLICATE'),
        ('H6_space_collapse_zip', h6_space_collapse, 'DUPLICATE'),
        ('H7_dba_strip',          h7_dba_strip, 'DUPLICATE'),
        ('H8_abbrev_expansion',   h8_abbrev_expansion, 'DUPLICATE'),
        ('H9_token_containment',  h9_token_containment, 'DUPLICATE'),
        ('H10_sparse_whitespace', h10_sparse_whitespace, 'DUPLICATE'),
        ('H11_acronym_match', h11_acronym_match, 'DUPLICATE'),
        ('H12_activity_suffix', h12_activity_suffix_prefix, 'DUPLICATE'),
    ]

    # Per-rule evaluation
    report = {'n_pairs': len(pairs), 'llm_verdicts': {
        'DUPLICATE': total_dup, 'RELATED': total_rel, 'DIFFERENT': total_diff}}
    print()
    print(f'{"Rule":25s} {"Fires":>7s} {"DUP":>6s} {"REL":>6s} {"DIFF":>6s} {"Prec":>7s} {"Recall":>8s}')
    print('-' * 75)

    per_rule_fires = {}
    for rule_name, fn, target in rules:
        fires = []
        vc = Counter()
        for p in pairs:
            key = (p['id1'], p['id2'])
            v = verdicts.get(key)
            if not v:
                continue
            if fn(p):
                fires.append(key)
                vc[v['verdict']] += 1
        per_rule_fires[rule_name] = set(fires)

        n = len(fires)
        dup = vc['DUPLICATE']; rel = vc['RELATED']; diff = vc['DIFFERENT']
        if target == 'DUPLICATE':
            prec = dup / n if n else 0
            recall = dup / total_dup if total_dup else 0
        else:  # NOT_DUPLICATE (for H4 anti-rule)
            not_dup = rel + diff
            prec = not_dup / n if n else 0
            recall = (rel + diff) / (total_rel + total_diff) if (total_rel+total_diff) else 0

        print(f'{rule_name:25s} {n:>7,} {dup:>6,} {rel:>6,} {diff:>6,} '
              f'{100*prec:>6.1f}% {100*recall:>7.2f}%')

        report.setdefault('rules', {})[rule_name] = {
            'target': target,
            'fires': n,
            'llm_dup': dup, 'llm_rel': rel, 'llm_diff': diff,
            'precision': round(prec, 4),
            'recall': round(recall, 4),
        }

    # Combined gate: (any positive rule) AND NOT H4
    pos_rules = [
        'H1_punct_invariant', 'H2_legal_form_agnostic', 'H3_cross_src_zip_name',
        'H5_decorations_strip', 'H6_space_collapse_zip', 'H7_dba_strip',
        'H8_abbrev_expansion', 'H9_token_containment', 'H10_sparse_whitespace',
        'H11_acronym_match', 'H12_activity_suffix',
    ]
    pos = set()
    for k in pos_rules:
        pos |= per_rule_fires[k]
    neg = per_rule_fires['H4_series_anti_dup']
    combined = pos - neg
    vc = Counter()
    for k in combined:
        v = verdicts.get(k)
        if v:
            vc[v['verdict']] += 1
    n = len(combined); dup = vc['DUPLICATE']; rel = vc['RELATED']; diff = vc['DIFFERENT']
    prec = dup / n if n else 0
    recall = dup / total_dup if total_dup else 0
    print('-' * 75)
    print(f'{"COMBINED (H1|H2|H3)&~H4":25s} {n:>7,} {dup:>6,} {rel:>6,} {diff:>6,} '
          f'{100*prec:>6.1f}% {100*recall:>7.2f}%')
    report['combined_gate'] = {
        'rule': '(H1 OR H2 OR H3) AND NOT H4',
        'fires': n,
        'llm_dup': dup, 'llm_rel': rel, 'llm_diff': diff,
        'precision': round(prec, 4),
        'recall': round(recall, 4),
    }

    # Also: the heuristic auto_duplicate classifier vs LLM (as baseline)
    auto_dup_keys = {(p['id1'], p['id2']) for p in pairs if p['classification'] == 'auto_duplicate'}
    vc = Counter()
    for k in auto_dup_keys:
        v = verdicts.get(k)
        if v:
            vc[v['verdict']] += 1
    n = len(auto_dup_keys); dup = vc['DUPLICATE']; rel = vc['RELATED']; diff = vc['DIFFERENT']
    prec = dup / n if n else 0
    recall = dup / total_dup if total_dup else 0
    print(f'{"BASELINE heuristic_auto":25s} {n:>7,} {dup:>6,} {rel:>6,} {diff:>6,} '
          f'{100*prec:>6.1f}% {100*recall:>7.2f}%')
    report['baseline_heuristic_auto_dup'] = {
        'rule': 'existing heuristic auto_duplicate',
        'fires': n,
        'llm_dup': dup, 'llm_rel': rel, 'llm_diff': diff,
        'precision': round(prec, 4),
        'recall': round(recall, 4),
    }

    # Stacked gates: require N+ positive rules to fire (boosts precision)
    print()
    print('Stacked gates (N+ positive rules fire AND NOT H4):')
    print(f'{"Gate":25s} {"Fires":>7s} {"DUP":>6s} {"REL":>6s} {"DIFF":>6s} {"Prec":>7s} {"Recall":>8s}')
    pos_sets = [per_rule_fires[k] for k in pos_rules]
    # Count per-pair rule fires
    pair_rule_counts = Counter()
    for s in pos_sets:
        for k in s:
            pair_rule_counts[k] += 1
    for threshold in [1, 2, 3, 4]:
        gate = {k for k, n in pair_rule_counts.items() if n >= threshold} - neg
        vc = Counter()
        for k in gate:
            v = verdicts.get(k)
            if v:
                vc[v['verdict']] += 1
        n = len(gate); dup = vc['DUPLICATE']; rel = vc['RELATED']; diff = vc['DIFFERENT']
        prec = dup / n if n else 0
        recall = dup / total_dup if total_dup else 0
        print(f'  N>={threshold:1d} positive rules      {n:>7,} {dup:>6,} {rel:>6,} {diff:>6,} '
              f'{100*prec:>6.1f}% {100*recall:>7.2f}%')
        report.setdefault('stacked_gates', {})[f'N>={threshold}'] = {
            'fires': n, 'llm_dup': dup, 'llm_rel': rel, 'llm_diff': diff,
            'precision': round(prec, 4), 'recall': round(recall, 4),
        }

    # Specific high-value combinations
    print()
    print('Specific rule combinations (AND-ed) minus H4:')
    combos = [
        ('H2 AND H6',  per_rule_fires['H2_legal_form_agnostic'] & per_rule_fires['H6_space_collapse_zip']),
        ('H2 AND H3',  per_rule_fires['H2_legal_form_agnostic'] & per_rule_fires['H3_cross_src_zip_name']),
        ('H6 AND H3',  per_rule_fires['H6_space_collapse_zip'] & per_rule_fires['H3_cross_src_zip_name']),
        ('H5 AND H6',  per_rule_fires['H5_decorations_strip'] & per_rule_fires['H6_space_collapse_zip']),
        ('H9 AND H3',  per_rule_fires['H9_token_containment'] & per_rule_fires['H3_cross_src_zip_name']),
        ('H9 AND zip_same_src', per_rule_fires['H9_token_containment']),   # H9 alone, already requires same ZIP
        ('H10 alone', per_rule_fires['H10_sparse_whitespace']),
    ]
    for name, s in combos:
        s = s - neg
        vc = Counter()
        for k in s:
            v = verdicts.get(k)
            if v:
                vc[v['verdict']] += 1
        n = len(s); dup = vc['DUPLICATE']; rel = vc['RELATED']; diff = vc['DIFFERENT']
        prec = dup / n if n else 0
        recall = dup / total_dup if total_dup else 0
        print(f'  {name:25s} {n:>7,} {dup:>6,} {rel:>6,} {diff:>6,} '
              f'{100*prec:>6.1f}% {100*recall:>7.2f}%')

    # How many LLM-DUPs does the combined gate MISS, and what do they look like?
    dup_keys = {k for k, v in verdicts.items() if v['verdict'] == 'DUPLICATE'}
    missed = dup_keys - combined
    print(f'\\nLLM-DUPs missed by combined gate: {len(missed):,} / {len(dup_keys):,}')
    # Sample 10 missed
    by_key = {(p['id1'], p['id2']): p for p in pairs}
    sample_missed = []
    for k in list(missed)[:10]:
        p = by_key.get(k)
        if p:
            sample_missed.append({
                'id1': k[0], 'id2': k[1],
                'name1': p.get('display_name_1'),
                'name2': p.get('display_name_2'),
                'src1': p.get('source_1'),
                'src2': p.get('source_2'),
                'zip_match': p['scores'].get('zip5_match'),
                'name_std': p['scores'].get('name_standard_sim'),
                'name_agg': p['scores'].get('name_aggressive_sim'),
            })
    print('\\nSample of missed LLM-DUPs (for rule iteration):')
    for s in sample_missed:
        print(f'  {s["src1"]:>10s} <-> {s["src2"]:<10s} '
              f'zip_match={s["zip_match"]} name_std={s["name_std"]:.2f}')
        print(f'    A: {(s["name1"] or "")[:55]}')
        print(f'    B: {(s["name2"] or "")[:55]}')
    report['missed_sample'] = sample_missed
    report['missed_count'] = len(missed)

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, default=str)
    print(f'\\nFull report: {OUT_JSON}')


if __name__ == '__main__':
    main()
