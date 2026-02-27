# CBA Provision Extractor — Fix Rules Based on Human Review

## Context

We ran the rule-based CBA provision extractor on the 32BJ Apartment Building Agreement (SEIU Local 32BJ / Realty Advisory Board, 2022–2026, 162 pages). It extracted 82 provisions. A human reviewer evaluated every single one. Results:

- **36 APPROVED** (correctly extracted and categorized)
- **13 DELETED** (false positives — not real provisions)
- **22 RECATEGORIZED** (real provisions, wrong category)
- **11 FLAGGED AS NOTE** (need attention — truncated, ambiguous, or dual-topic)

**Overall accuracy: 44% clean on first pass.** The problems are concentrated in a few specific rules. Here are the fixes needed, ordered by impact.

---

## FIX 1: Page-Range Filter (eliminates 11 false positives)

**Problem:** The extractor grabs text from the Table of Contents (pages 1–7) and the Index (pages 150–153). These are just topic headings with page numbers like "Military Service...97" or "Jury Duty...110" — not actual contract provisions.

**Deleted provision IDs from TOC/Index:** 615, 616, 617, 689, 690, 691, 692, 693, 694, 695, 696

**Fix:** Add a page-range filter that skips extraction on:
- The first ~5% of pages in any CBA (catches the Table of Contents)
- The last ~3% of pages (catches the Index)
- OR detect the dotted-line pattern (sequences of `.` or `·` characters followed by page numbers) as a TOC/Index signature and skip any text block containing that pattern

**Detection heuristic for TOC/Index lines:**
```
# Match lines like "Military Service ...............97" or "Subject    Page"
regex: r'\.{4,}|·{4,}|\.\s*\.\s*\.\s*\.|\bSubject\s+Page\b'
```

---

## FIX 2: `coverage_tiers` Rule (15 false positives — worst offender)

**Problem:** This rule matches on the words "individual" and "family" way too broadly. It's supposed to find health insurance tier language (individual vs. family coverage), but instead it's matching:

| What it matched | What the text actually is |
|---|---|
| "no **individual** shall have the right to settle any claim" | Grievance procedure rule |
| "Death in **Family**" | Bereavement leave |
| "**individual** locker and key" | Sanitary facilities / working conditions |
| "**individual** attorneys representing them" | Discrimination claims protocol |
| "**individual** employee" (multiple times) | Discrimination claims protocol |
| "**individual** Superintendent" | Superintendent discharge arbitration |
| "**individually** negotiated" | Special superintendent agreements |
| "**family** leave" | NYS Paid Family Leave |
| "**individual** or multi-plaintiff" | Mediation requirements |

**False positive provision IDs:** 623, 639, 647, 649, 659, 662, 669, 670, 671, 672, 675, 677, 685, 687, 694

**Fix:** Tighten the `coverage_tiers` rule so "individual" and "family" only trigger when they appear near health-insurance-specific context words. Require at least one of the following within ~50 words:
- "plan", "coverage", "premium", "enrollment", "tier", "dependent", "deductible", "copay", "coinsurance", "HMO", "PPO", "health fund", "benefit fund", "medical", "dental", "vision", "prescription"

**Negative context (do NOT match if these appear nearby):**
- "attorney", "locker", "leave", "arbitration", "claim", "settle", "negotiate", "superintendent", "plaintiff", "protocol", "death"

---

## FIX 3: `just_cause` Rule (4 false positives)

**Problem:** The rule matches "good cause" in procedural contexts that have nothing to do with employee discipline. The phrase "good cause" appears in CBAs for many reasons:
- Arbitrators extending deadlines "for good cause shown"
- Union/RAB presidents waiving provisions "for good cause"  
- Mailing deadline exceptions for "compelling good cause"

But REAL just cause provisions use different language:
- "termination of employment for any reason other than **just cause**" (#666 — CORRECT match)
- "disciplinary action...shall only be for **just cause**" (#681 — CORRECT match)

**False positive provision IDs:** 620, 625 (duplicate, deleted), 630, 674
**Also borderline:** 656 (medical leave return — "good cause shown" — flagged as NOTE), 663 (recall/hiring rights, not discipline — recategorized to seniority)

**Fix:**
1. Make "just cause" (exact phrase) HIGH confidence (0.9+)
2. Make "good cause" LOW confidence (0.5) and require nearby discipline-context words: "discharge", "discipline", "disciplinary", "termination", "terminate", "dismiss", "dismissal", "fire", "fired", "suspend", "suspension", "penalty"
3. If "good cause" appears near "waive", "waiver", "extend", "extension", "deadline", "time limit", "bypass", "notice" — do NOT match as just_cause. These are procedural uses.
4. If "good cause" appears near "arbitrator", "arbitration" and NOT near discipline words — do NOT match.

---

## FIX 4: `training_program` Rule (5 false positives)

**Problem:** Matches any mention of "training" regardless of who is being trained or what the training is for.

| What it matched | What it actually is |
|---|---|
| "Union shall provide training opportunity to the Employer to facilitate electronic records" (×2) | Union training employers on dues systems — union_security |
| "Pension, Health, Legal and **Training** Fund contributions" | Wage parity provision — wages |
| "except that they are eligible to participate in the **Training** Fund" | Benefit fund exclusion for vacation relief — other |

**Real training provision (#676):** "The Employer shall compensate, at straight-time pay, any employee...for any time required for the employee to attend any instruction or **training** program" — CORRECT match.

**False positive provision IDs:** 619, 621, 651, 661, 696 (index, deleted)

**Fix:**
1. Require "training" to appear with employee-as-trainee context: "employee shall attend", "required to attend", "training program", "instruction or training", "complete training", "training course"
2. Do NOT match when "training" appears as part of "Training Fund" unless the sentence is specifically about the training program itself (not just listing funds)
3. Do NOT match when the union is providing training TO the employer (look for "Union shall provide training" + "to the Employer" pattern)

---

## FIX 5: `jury_duty` Rule (2 false positives beyond TOC)

**Problem:** Provision #622 matched because "jury duty" appears in a list within a maintenance-of-standards clause: "wages, hours, sick pay, vacations, holidays, relief periods, jury duty, or group life insurance." The rule should not fire when "jury duty" is just one item in a list of many topics.

**Fix:** If "jury duty" appears in a comma-separated list of 3+ other labor topics (wages, hours, holidays, sick pay, vacations, insurance, etc.), classify as "other" (maintenance of standards), not "leave/jury_duty."

---

## FIX 6: Duplicate Detection

**Problem:** Two cases of the same text extracted twice by different rules:
- #624 and #625: Same "good cause shown" sentence — one as arbitrator_authority (correct), one as just_cause (wrong). **Deleted #625.**
- #677 and #678: Same "Death in Family" text — one as coverage_tiers (wrong), one as holiday_pay (wrong, it's bereavement). **Deleted #678.**

**Fix:** After all rules run, deduplicate by comparing provision_text. If two provisions share >80% text overlap on the same page, keep the one with higher confidence score and discard the other.

---

## FIX 7: Text Truncation

**Problem:** Three provisions had text that cut off mid-sentence:
- #640: "paid either for illnesses..." (stops at page break)
- #650: Just the tail end of a successorship clause
- #682: "safety committees will..." (stops mid-sentence)

**Fix:** When extracting provision text, check if the last sentence is complete (ends with period, semicolon, or colon). If not, continue extracting into the next text block or page until a sentence boundary is found. Set a max continuation of ~200 additional characters to avoid runaway extraction.

---

## FIX 8: Article Reference Parsing

**Problem:** Many provisions in the discrimination protocol section (pages 105–130) show the article reference as "Article 19, Section 1981" — but "1981" comes from "Section 1981" of the Civil Rights Act, which appears in the text. The parser is grabbing statutory references instead of contract article numbers.

**Affected provisions:** 668, 669, 670, 671, 672, 673, 674, 675, 676, 677, 678, 679, 680, 681, 682, 683, 684, 685

**Fix:** When parsing article references, prefer the article/section structure at the TOP of the page or section header over references found inline in body text. If a "Section" number is > 100, it's almost certainly a statutory reference (like Section 1981 of the Civil Rights Act, Section 350 of the Workers' Comp Law, etc.) and should not be used as the contract section number.

---

## FIX 9: Context Window for Extraction (from reviewer feedback)

**Reviewer note on #618:** "This makes the case for more contextualization when showing sections of the contract, possibly 100 characters prior and after with the specific section highlighted."

**Fix:** When extracting a provision, also capture ~100 characters before and after the matched text and store them in separate fields (`context_before`, `context_after`). Display these in the review interface as dimmed text flanking the highlighted provision. This helps reviewers understand WHY a rule fired without having to go back to the original PDF.

---

## Summary of Reviewed Category Corrections to Apply

These are the final human-confirmed category assignments for provisions that were recategorized:

```
#619: training → other
#620: job_security → union_security
#621: training → union_security  
#622: leave → other
#634: healthcare → pension
#639: healthcare → leave
#647: healthcare → other
#649: healthcare → job_security
#651: training → wages
#659: healthcare → leave
#661: training → other
#662: healthcare → other
#663: job_security → seniority
#664: union_security → seniority
#669: healthcare → other
#670: healthcare → grievance
#671: healthcare → grievance
#672: healthcare → grievance
#674: job_security → other
#675: healthcare → other
#677: healthcare → leave
#687: healthcare → grievance
```

---

## Files

- `32bj_provisions_FINAL.json` — The 69 surviving provisions with corrected categories and review notes. Use this as ground truth for testing rule changes.
- `32bj_review_decisions.json` — Full review audit trail with human decisions on all 82 original provisions.

## Priority Order

1. **Page-range filter** (easiest, eliminates 11 false positives instantly)
2. **coverage_tiers context window** (biggest single rule problem, 15 FPs)
3. **just_cause "good cause" fix** (4 FPs, plus makes the rule more precise)
4. **Duplicate detection** (prevents the same text appearing twice)
5. **training_program context** (5 FPs)  
6. **Text truncation fix** (3 incomplete provisions)
7. **Article reference parser** (18 wrong article refs)
8. **Context window capture** (reviewer UX improvement)
9. **jury_duty list detection** (2 FPs, lower priority)
