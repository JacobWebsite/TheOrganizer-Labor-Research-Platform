# LM2 vs F7 Membership Analysis (2026-02-13)

## Script
`scripts/analysis/compare_lm2_vs_f7.py`

## Overall Totals
- Dedup LM2 members: **14,507,547** (via `union_hierarchy.count_members=TRUE`)
- F7 bargaining unit workers: **15,774,553** (via `f7_union_employer_relations.bargaining_unit_size`)
- Overall ratio: **108.7%** (F7 slightly exceeds dedup)
- F7 employers: 105,647 | F7 locals with employer data: 7,500

## Coverage Categories
- 56 unions have both dedup + F7 data
- 81 unions have dedup only (no F7 filings)
- 15 entries have F7 only (no dedup membership)

## Three Key Patterns

### 1. Public Sector Unions: ~0% F7 Coverage (TO RESOLVE)
F7 filings only cover private-sector employers. These unions have members but no F7 data:
| Union | Dedup Members | F7 Workers | Why |
|-------|-------------|-----------|-----|
| NEA | 2,839,808 | 0 | Public education |
| AFT | 1,799,290 | 73,394 (4.1%) | Mostly public teachers |
| NFOP | 373,186 | 170 | Police |
| NNU | 215,151 | 0 | Nurses, largely public |
| NPMHU | 124,592 | 0 | Postal mail handlers |
| RLCA | 109,369 | 0 | Rural letter carriers |
| NTEU | 93,501 | 0 | Treasury employees |
| SAGAFTRA | 87,966 | 0 | Actors/media (freelance) |
| ALPA | 78,317 | 0 | Airline pilots |
| APWU | 63,212 | 0 | Postal workers |
| AFSCME | 59,183 | 174,514 (294.9%) | State/county/muni (mixed) |
| NALC | 34,822 | 0 | Letter carriers |
| UNAFF locals | 492,911 | 0 | Various unaffiliated |

**Resolution needed:** These unions' employers won't appear in F7. Public-sector employer data must come from other sources (NLRB public-sector filings, state labor boards, government payroll data).

### 2. Building Trades / Entertainment: Massive F7 Over-Coverage (10x-32x)
LM2 counts dues-paying members; F7 counts all covered workers. Building trades rotate workers through union job sites without formal membership.
| Union | Dedup | F7 | Ratio | Why |
|-------|-------|-----|-------|-----|
| USW | 18,125 | 588,656 | 32.5x | Steelworkers, open-shop coverage |
| PPF | 23,000 | 671,353 | 29.2x | Plumbers, hiring hall model |
| IATSE | 24,393 | 651,188 | 26.7x | Stage/entertainment, project-based |
| IUOE | 75,851 | 1,689,663 | 22.3x | Operating engineers, project-based |
| BSOIW | 9,566 | 174,820 | 18.3x | Iron workers |
| IBEW | 46,665 | 691,082 | 14.8x | Electricians |
| UAW | 64,622 | 773,180 | 12.0x | Auto workers |
| OPEIU | 11,390 | 163,891 | 14.4x | Office/professional |
| IAM | 56,617 | 412,749 | 7.3x | Machinists |
| CWA | 38,750 | 214,053 | 5.5x | Communications workers |

**Resolution needed:** When comparing membership to covered workers, the ratio itself is a meaningful metric ("coverage multiplier"). Could flag building-trades unions so the platform doesn't treat high F7 as inflated membership. Consider adding a `coverage_multiplier` column or `sector_type` (building_trades/industrial/public/service) flag.

### 3. Orphaned F7 Union File Numbers (195 unions, 92,627 workers, 812 employers)
195 union file numbers in `f7_union_employer_relations` have NO entry in `union_hierarchy` or `unions_master`.
- Largest: f_num 12590 (75 employers, 38,192 workers)
- Second: f_num 18001 (113 employers, 13,619 workers)
- These are likely defunct unions, recently formed unions, or data entry errors.

**Resolution needed:**
1. Query OLMS API or historical LM filings to identify these f_nums
2. Add them to `unions_master` + `union_hierarchy` or mark as defunct
3. 92K workers is significant -- worth recovering

## Key Tables / Views Used
- `union_hierarchy` -- `count_members`, `parent_fnum`, `hierarchy_level`, `members_2024`
- `v_union_members_counted` -- authoritative dedup (14.5M)
- `f7_union_employer_relations` -- `employer_id`, `union_file_number`, `bargaining_unit_size`
- `f7_employers_deduped` -- 60,953 deduplicated employers (50,273 active)
- `unions_master` -- `f_num`, `aff_abbr`, `union_name`, `members`

## Methodology
1. International unions with `count_members=TRUE`: use `members_2024` directly
2. Locals with `count_members=TRUE` (unaffiliated): aggregate by `aff_abbr`
3. F7: map each local's `union_file_number` up to `parent_fnum` to get national, sum `bargaining_unit_size`
4. Join on national f_num; unaffiliated join on aff_abbr
