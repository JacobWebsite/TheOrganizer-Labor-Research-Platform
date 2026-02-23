# I16 990/BMF Matching Quality Audit

## Summary
- 990 source table used: `national_990_filers`
- Active 990 matches: **13,872**
- Active BMF matches: **9**
- 990 methods observed: **7**

## Method Distribution (990)
| Method | Count | Percent | Avg confidence |
|---|---:|---:|---:|
| EIN_EXACT | 11,595 | 83.6% | 1.000 |
| FUZZY_TRIGRAM | 786 | 5.7% | 0.762 |
| FUZZY_SPLINK_ADAPTIVE | 737 | 5.3% | 0.962 |
| NAME_CITY_STATE_EXACT | 384 | 2.8% | 0.950 |
| NAME_AGGRESSIVE_STATE | 228 | 1.6% | 0.750 |
| NAME_STATE_EXACT | 125 | 0.9% | 0.900 |
| NAME_AGGRESSIVE_STATE_CITY_RESOLVED | 17 | 0.1% | 0.750 |

## EIN Validation
- 990 active matches with `EIN_EXACT`: **11,595**
- `EIN_EXACT` matches verifiable via `national_990_f7_matches` EIN path: **11,595**
- Legacy-EIN verification rate: **100.0%**
- Note: `f7_employers_deduped` has no EIN column; target-side EIN validation uses `national_990_f7_matches` as proxy.

## Potential Coverage Gaps
- Legacy 990->F7 links not present as active UML rows (sampled): **20**
- n990_id=100002 ein=844720550 -> f7=f3e11b3525a6073e
- n990_id=100079 ein=202808129 -> f7=66cd0e2ddf5ff582
- n990_id=100087 ein=454597576 -> f7=f6fda2da9f68c021
- n990_id=100261 ein=911882464 -> f7=1660f0c1d12b49a6
- n990_id=100308 ein=263903732 -> f7=fedaf55ba5a03cdc
- n990_id=100343 ein=743050638 -> f7=4847f13a896b0635
- n990_id=100401 ein=823993389 -> f7=d25a4480afbe7f8f
- n990_id=100478 ein=590931515 -> f7=b20c4e3de9d459b3
- n990_id=100530 ein=421374894 -> f7=8e087ae89671f902
- n990_id=100617 ein=270014795 -> f7=de1cb37d349b47ed
- n990_id=100622 ein=866052414 -> f7=ba2a25067bac9d2b
- n990_id=100663 ein=205819352 -> f7=617de9e6f242d64b
- n990_id=100761 ein=431874616 -> f7=aac1e7e9ac46a6d6
- n990_id=100810 ein=920160240 -> f7=175188332d948a9e
- n990_id=100858 ein=382262287 -> f7=e5c3c7569f0ab0d0
- n990_id=100901 ein=680234567 -> f7=3d1f43daa64dd37d
- n990_id=100911 ein=770549615 -> f7=d15fd47ab173ea5f
- n990_id=100993 ein=950488945 -> f7=7d537c4a4d405e03
- n990_id=101040 ein=570646037 -> f7=ade6236aaa6e0122
- n990_id=101089 ein=453651131 -> f7=fedaf55ba5a03cdc

- High-similarity name+state candidates with no active 990 match (sampled): **0**

## Quality Risks
- Active 990 matches with extracted name_similarity < 0.85: **1,262**
- UML `2159784` sim=0.714 | EPIC MEDICAL SERVICES PC -> PHS Medical Services PC
- UML `2211083` sim=0.833 | LOUISIANA BANKERS ASSOCIATION -> Louisiana Association of Educators
- UML `2181363` sim=0.710 | Mental Health of Associates -> Dental Health Associates
- UML `2166055` sim=0.810 | Hartwick College -> ARA @ HARTWICK COLLEGE
- UML `2144900` sim=0.815 | PORTLAND KARTING ASSOCIATION -> Portland Opera Association
- UML `2168905` sim=0.829 | Civil Service Employee Association -> Civil Service Employees Association, Inc
- UML `2143790` sim=0.818 | ROGUE COMMUNITY COLLEGE FOUNDATION -> Rogue Community College District
- UML `2254518` sim=0.821 | UNIVERSITY CLUB OF CHICAGO -> University of Chicago Lab Schools
- UML `2143647` sim=0.833 | HAWAII DENTAL ASSOCIATION -> Hawaii International Film Association
- UML `2264028` sim=0.724 | American Legion Post 0237 -> American Legion Post 91
- UML `2236682` sim=0.797 | INTERNATIONAL BROTHERHOOD OF ELECTRICAL WORKERS 117 -> International Brotherhood of Electrical Workers Local 702
- UML `2241330` sim=0.714 | Greater Chicago Ferret Association -> Fence Association of Greater Chicago
- UML `2233787` sim=0.847 | CALIFORNIA PILOTS ASSOCIATION -> California Faculty Association
- UML `2143691` sim=0.812 | IMPACT HARRISBURG -> Harrisburg PDCA
- UML `2160671` sim=0.755 | FOWLER HOUSING DEVELOPMENT FUND COMPANY INC -> 400-408 Housing Development Fund Company Inc.
- UML `2163653` sim=0.823 | INTERNATIONAL BROTHERHOOD OF ELECTRICAL WORKERS LOCAL UNION -> International Brotherhood of Electrical Workers Local 4 (IBEW)
- UML `2248310` sim=0.720 | United Steelworkers International Local Union 07139 -> United Steelworkers International Union (USW)
- UML `2255289` sim=0.800 | CALIFORNIA GROCERS ASSOCIATION -> California Faculty Association
- UML `2211639` sim=0.824 | LOUISIANA ASSOCIATION OF BROADCASTERS -> Louisiana Association of Educators
- UML `2259754` sim=0.823 | INTERNATIONAL BROTHERHOOD OF ELECTRICAL WORKERS LOCAL NO 538 -> International Brotherhood of Electrical Workers Local 702

- Potential entity-type mismatches (heuristic sample): **20**
- UML `2138958` ntee=None | The Oltmans Construction Co Foundation -> Manson Construction
- UML `2229763` ntee=None | CATHOLIC CHARITIES NEIGHBORHOOD SERVICES INC -> Catholic Charities Neighborhood Services Inc.
- UML `2208676` ntee=None | THE BEVERLY PEPPER FOUNDATION -> Harvard University Dining Services
- UML `2231014` ntee=None | UB FOUNDATION SERVICES INC -> DD Services, Inc.
- UML `2231571` ntee=None | HALCYON FOUNDATION -> Catholic Community Services of Western Washington
- UML `2232241` ntee=None | PERFORMANCE FAMILY FOUNDATION INC -> Performance Environmental Services LLC
- UML `2253163` ntee=None | EMPLOYERS CONTRACT ADMINISTRATION FUND -> Associated General Contractors of Northern Nevada
- UML `2253510` ntee=None | LUTHERAN SOCIAL SERVICES FOUNDATION OF UPSTATE NEW YORK INC -> Lutheran Social Services of New York
- UML `2253512` ntee=None | WILLIAM HOWARD CHARITABLE TRUST -> Ragnar Benson Construction, LLC
- UML `2253661` ntee=None | AMERICAN SOCIETY FOR CONCRETE CONTRACTORS -> M & H CONCRETE CONTRACTORS INC.
- UML `2253926` ntee=None | TURNER CONSTRUCTION COMPANY FOUNDATION -> G AND M CONSTRUCTION
- UML `2253963` ntee=None | MESSER CONSTRUCTION FOUNDATION -> Mosser Construction
- UML `2254001` ntee=None | HUNTERS POINT WATERFOWL FOUNDATION -> A.J. ROSE MANUFACTURING COMPANY
- UML `2254012` ntee=None | GEORGIA LEGAL FOUNDATION INC -> Georgia Legal Services 
- UML `2254049` ntee=None | PHI SIGMA IOTA FOREIGN LANGUAGE NATIONAL HONOR SOCIETY -> Parkhurst Dining Services at Allegheny College
- UML `2254115` ntee=None | FRESENIUS MEDICAL CARE FOUNDATION INC -> New York Dialysis Services
- UML `2254140` ntee=None | THE FRANCIS ASBURY PALMER FOUNDATION C/O KLINGENSTEIN FIELDS ADVISORS -> G&E Real Estate Management Services, Inc.
- UML `2138919` ntee=None | WASHINGTON DC COMMUNITY YOUTH FOUNDATION INC -> Paving Contractors signed with Local 77
- UML `2138937` ntee=None | ASPLUNDH FOUNDATION -> Asplundh Construction, LLC
- UML `2138994` ntee=None | PEARL FOUNDATION INC -> Staff Pro/ Guma Construction 

## Recommendations
- Resolve low-similarity (<0.85) 990 matches with manual review or stricter floor in fallback fuzzy path.
- Reconcile legacy `national_990_f7_matches` links into `unified_match_log` or formally deprecate unmatched legacy rows.
- Consider adding EIN crosswalk for F7 targets to enable direct EIN validation beyond legacy bridge.
