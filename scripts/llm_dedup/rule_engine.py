"""
Production rule engine for LLM-free employer-pair dedup classification.

Given a candidate pair, returns one of:
  - tier_series_demoted : H4 fired; pair is series/numbered variant, NEVER merge
  - tier_A_auto_merge   : >=96% precision; safe to apply as master_employer_merge_log
  - tier_B_high_conf    : 90-95% precision; apply with light human spot-check
  - tier_C_review       : 50-90% precision; manual review queue
  - tier_D_different    : no rule fires; treat as heuristic auto_different

Validated against 31,532 Haiku-labeled pairs (2026-04-16 NY singleton batch).
Target precision-vs-recall profile when applied to that dataset:
  Tier A alone : 96.0% precision, 56% recall of real DUPs (~145 of 258)
  Tier A+B     : ~91%  precision, 76% recall           (~200 of 258)
  Tier A+B+C   : ~55%  precision, 83% recall           (~215 of 258)

Higher recall than this requires LLM judgment -- the remaining ~17% of
real DUPs are genuinely hard (subsidiary relationships, cross-ZIP d/b/a,
semantic abbreviation) that rule patterns over-generalize on.
"""
import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Shared normalizers (same as validate_heuristic_rules.py)
# ---------------------------------------------------------------------------

LEGAL_SUFFIX_RE = re.compile(
    r'\b('
    r'llc|l\.l\.c|inc|incorporated|corp|corporation|company|co|ltd|limited|'
    r'lp|l\.p|llp|l\.l\.p|pc|p\.c|pllc|pa|p\.a|na|n\.a|sa|s\.a|'
    r'gmbh|plc|ag|bv|nv|se|srl|sarl|the|of|and|an|a|nq'
    r')\b',
    re.IGNORECASE,
)
PUNCT_RE = re.compile(r'[^\w\s]')
MULTISPACE_RE = re.compile(r'\s+')

PAREN_RE = re.compile(r'\s*[\(\[\{][^\)\]\}]*[\)\]\}]\s*')
AT_SUFFIX_RE = re.compile(r'\s*@\s+.+$', re.IGNORECASE)
DBA_RE = re.compile(r'\s+d[\./]?b[\./]?a\s+.+$', re.IGNORECASE)
SLASH_SUFFIX_RE = re.compile(r'\s+/\s+.+$')
COMMA_SECOND_CLAUSE_RE = re.compile(
    r',\s+(?!(?:llc|l\.l\.c|inc|corp|ltd|lp|co|pllc|pc|pa)\b).+$', re.IGNORECASE
)

ROMAN = r'(?:i{1,3}|iv|v|vi{0,3}|ix|x{1,3}|xi{0,3}|xiv|xv|xvi{0,3}|xix|xx)'
TRAILING_TOKEN = re.compile(
    rf'\s+(?:'
    rf'\d+|{ROMAN}|series\s*[a-z0-9]+|ser\s*[a-z0-9]+|fund\s*[a-z0-9]+|'
    rf'trust\s*[a-z0-9]+|chapter\s*[a-z0-9]+|local\s*\d+|[a-z]'
    rf')$', re.IGNORECASE,
)

ABBREV = {
    'hosp': 'hospital', 'ctr': 'center', 'cntr': 'center', 'cntrl': 'central',
    'assn': 'association', 'dept': 'department', 'natl': 'national',
    'govt': 'government', 'mfg': 'manufacturing', 'mgmt': 'management',
    'sys': 'systems', 'svcs': 'services', 'svc': 'service',
    'intl': 'international', 'univ': 'university', 'inst': 'institute',
    'bldg': 'building', 'constr': 'construction', 'dev': 'development',
    'dist': 'distribution', 'environ': 'environmental', 'equip': 'equipment',
    'engr': 'engineering', 'eng': 'engineering', 'maint': 'maintenance',
    'amer': 'american', 'med': 'medical',
}

ACRONYM_STOPWORDS = {'the', 'of', 'and', 'a', 'an', 'in', 'for', 'at', 'by', 'to',
                     'or', 'on', 'with', 'as', 'llc', 'inc', 'corp', 'ltd', 'lp',
                     'llp', 'co', 'pc', 'pa', 'pllc'}

ACTIVITY_TOKENS = {
    'production', 'packing', 'packaging', 'services', 'service', 'operations',
    'management', 'distribution', 'logistics', 'solutions', 'systems',
    'technologies', 'manufacturing', 'sales', 'marketing', 'consulting',
    'development', 'holdings', 'enterprises', 'partners', 'group',
    'international', 'inc', 'corp', 'corporation', 'llc', 'ltd', 'co',
    'limited', 'incorporated',
}


def normalize_punct_only(name):
    if not name:
        return ''
    n = name.lower()
    n = PUNCT_RE.sub(' ', n)
    return MULTISPACE_RE.sub(' ', n).strip()


def normalize_all(name):
    if not name:
        return ''
    n = name.lower()
    n = PUNCT_RE.sub(' ', n)
    n = LEGAL_SUFFIX_RE.sub(' ', n)
    return MULTISPACE_RE.sub(' ', n).strip()


def strip_decorations(name):
    if not name:
        return ''
    n = name
    n = DBA_RE.sub('', n)
    n = SLASH_SUFFIX_RE.sub('', n)
    n = AT_SUFFIX_RE.sub('', n)
    n = PAREN_RE.sub(' ', n)
    n = COMMA_SECOND_CLAUSE_RE.sub('', n)
    return n


def normalize_h5(name):  return normalize_all(strip_decorations(name))
def normalize_h6(name):  return re.sub(r'\s+', '', normalize_all(name))


def normalize_h8(name):
    n = normalize_all(strip_decorations(name))
    return ' '.join(ABBREV.get(t, t) for t in n.split())


def _build_acronym(text):
    tokens = re.sub(r'[^\w\s]', ' ', text.lower()).split()
    return ''.join(t[0] for t in tokens
                   if t and t not in ACRONYM_STOPWORDS and t[0].isalpha())


# ---------------------------------------------------------------------------
# Rule predicates -- each takes a normalized dict + returns bool.
# Pair dict expected shape:
#   {
#     'display_name_1','display_name_2','canonical_name_1','canonical_name_2',
#     'source_1','source_2','zip_1','zip_2',
#     'name_standard_sim','name_aggressive_sim','zip5_match'
#   }
# ---------------------------------------------------------------------------

def h4_series_anti_dup(p):
    name1 = p.get('canonical_name_1') or p.get('display_name_1') or ''
    name2 = p.get('canonical_name_2') or p.get('display_name_2') or ''
    n1 = normalize_punct_only(name1); n2 = normalize_punct_only(name2)
    n1s = TRAILING_TOKEN.sub('', n1).strip()
    n2s = TRAILING_TOKEN.sub('', n2).strip()
    if not n1s or not n2s or len(n1s) < 8:
        return False
    return n1s == n2s and n1 != n2


def _name_pair(p):
    return (p.get('canonical_name_1') or p.get('display_name_1') or '',
            p.get('canonical_name_2') or p.get('display_name_2') or '')


def h1_punct_invariant(p):
    a, b = _name_pair(p)
    na = normalize_punct_only(a); nb = normalize_punct_only(b)
    return bool(na) and na == nb


def h2_legal_form_agnostic(p):
    a, b = _name_pair(p)
    na = normalize_all(a); nb = normalize_all(b)
    return bool(na) and na == nb and len(na) >= 4


def h3_cross_src_zip_name(p):
    s1 = (p.get('source_1') or '').strip()
    s2 = (p.get('source_2') or '').strip()
    if not s1 or not s2 or s1 == s2:
        return False
    if p.get('zip5_match', 0) < 1.0:
        return False
    return max(p.get('name_standard_sim', 0), p.get('name_aggressive_sim', 0)) >= 0.85


def h5_decorations_strip(p):
    a, b = _name_pair(p)
    na = normalize_h5(a); nb = normalize_h5(b)
    return bool(na) and bool(nb) and len(na) >= 5 and len(nb) >= 5 and na == nb


def h6_space_collapse_zip(p):
    if p.get('zip5_match', 0) < 1.0:
        return False
    a, b = _name_pair(p)
    na = normalize_h6(a); nb = normalize_h6(b)
    return bool(na) and bool(nb) and len(na) >= 6 and len(nb) >= 6 and na == nb


def h8_abbrev_expansion(p):
    a, b = _name_pair(p)
    na = normalize_h8(a); nb = normalize_h8(b)
    return bool(na) and bool(nb) and len(na) >= 5 and len(nb) >= 5 and na == nb


def h9_token_containment(p):
    if p.get('zip5_match', 0) < 1.0:
        return False
    a, b = _name_pair(p)
    na = normalize_h8(a); nb = normalize_h8(b)
    if not na or not nb:
        return False
    t1 = set(na.split()); t2 = set(nb.split())
    if len(t1) < 2 or len(t2) < 2:
        return False
    shorter, longer = (t1, t2) if len(t1) <= len(t2) else (t2, t1)
    if not shorter.issubset(longer):
        return False
    for tok in (longer - shorter):
        if tok.isdigit() or re.fullmatch(r'(?:' + ROMAN + ')', tok):
            return False
    return True


def h11_acronym_match(p):
    if p.get('zip5_match', 0) < 1.0:
        return False
    raw1 = p.get('display_name_1') or p.get('canonical_name_1') or ''
    raw2 = p.get('display_name_2') or p.get('canonical_name_2') or ''

    def candidates(raw):
        out = {normalize_punct_only(raw)}
        for m in re.findall(r'\(([^)]+)\)', raw):
            out.add(normalize_punct_only(m))
        return out

    c1, c2 = candidates(raw1), candidates(raw2)
    for a in c1:
        for b in c2:
            if not a or not b:
                continue
            short, long_ = (a, b) if len(a) < len(b) else (b, a)
            if len(short.split()) != 1 or not short.isalpha() or not (3 <= len(short) <= 10):
                continue
            if len(long_.split()) < 3:
                continue
            if _build_acronym(long_).lower() == short.lower():
                return True
    return False


def h12_activity_suffix(p):
    if p.get('zip5_match', 0) < 1.0:
        return False
    a, b = _name_pair(p)
    na = normalize_punct_only(a); nb = normalize_punct_only(b)
    if not na or not nb or na == nb:
        return False
    t1 = na.split(); t2 = nb.split()
    shorter, longer = (t1, t2) if len(t1) <= len(t2) else (t2, t1)
    if len(shorter) < 2 or len(longer) <= len(shorter):
        return False
    if longer[:len(shorter)] != shorter:
        return False
    extra = longer[len(shorter):]
    if not extra:
        return False
    if not all(t in ACTIVITY_TOKENS or t in {'and', 'of', 'the', 'for'} for t in extra):
        return False
    return True


# ---------------------------------------------------------------------------
# Tier engine
# ---------------------------------------------------------------------------

@dataclass
class Classification:
    tier: str                # tier_series_demoted | tier_A_auto_merge | tier_B_high_conf
                             # tier_C_review | tier_D_different
    rule: Optional[str]      # the rule (or combo) that fired
    predicted: str           # NOT_MERGE | DUPLICATE_HIGH | DUPLICATE_MED | REVIEW | DIFFERENT
    expected_precision: float  # from validation on 31,532 Haiku-labeled pairs


def classify_pair_v2(p) -> Classification:
    # H4 runs first as a short-circuit -- any pair differing only by a
    # trailing series/numeric is NEVER a true duplicate (100% precision).
    if h4_series_anti_dup(p):
        return Classification('tier_series_demoted', 'H4', 'NOT_MERGE', 1.00)

    # Tier A: >=96% precision combinations -- safe to auto-merge.
    if h2_legal_form_agnostic(p) and h3_cross_src_zip_name(p):
        return Classification('tier_A_auto_merge', 'H2+H3', 'DUPLICATE_HIGH', 0.96)
    if h6_space_collapse_zip(p) and h3_cross_src_zip_name(p):
        return Classification('tier_A_auto_merge', 'H6+H3', 'DUPLICATE_HIGH', 0.96)
    if h11_acronym_match(p):
        return Classification('tier_A_auto_merge', 'H11', 'DUPLICATE_HIGH', 1.00)

    # Tier B: 90-95% precision ONLY -- merge with light review.
    # H2+H6 is the only rule pairing that validated cleanly at 91% precision
    # when we exclude the Tier A cases (H2+H3, H6+H3). Standalone H6 and H12
    # drop to ~65-70% precision once those cases are removed, so they go
    # to Tier C (review queue) instead.
    if h2_legal_form_agnostic(p) and h6_space_collapse_zip(p):
        return Classification('tier_B_high_conf', 'H2+H6', 'DUPLICATE_MED', 0.91)

    # Tier C: 50-90% precision -- review queue.
    fired = []
    if h2_legal_form_agnostic(p):  fired.append('H2')
    if h5_decorations_strip(p):    fired.append('H5')
    if h6_space_collapse_zip(p):   fired.append('H6')   # residual standalone
    if h8_abbrev_expansion(p):     fired.append('H8')
    if h9_token_containment(p):    fired.append('H9')
    if h12_activity_suffix(p):     fired.append('H12')  # residual standalone
    if h3_cross_src_zip_name(p):   fired.append('H3')
    if h1_punct_invariant(p):      fired.append('H1')
    if fired:
        return Classification('tier_C_review', '+'.join(fired), 'REVIEW', 0.55)

    return Classification('tier_D_different', None, 'DIFFERENT', 0.99)


def pair_from_candidate(c) -> dict:
    """Adapter: unpack the candidates_singletons_scored.json row into the
    flat dict classify_pair_v2 expects."""
    s = c.get('scores', {})
    return {
        'display_name_1': c.get('display_name_1'),
        'display_name_2': c.get('display_name_2'),
        'canonical_name_1': c.get('canonical_name_1'),
        'canonical_name_2': c.get('canonical_name_2'),
        'source_1': c.get('source_1'),
        'source_2': c.get('source_2'),
        'zip_1': c.get('zip_1'),
        'zip_2': c.get('zip_2'),
        'name_standard_sim': s.get('name_standard_sim', 0),
        'name_aggressive_sim': s.get('name_aggressive_sim', 0),
        'zip5_match': s.get('zip5_match', 0),
    }
