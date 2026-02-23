# I15 WHD Matching Quality Audit

## Summary
- Source table used: `whd_cases`
- Active WHD matches: **12,355**
- Match methods observed: **7**
- Fuzzy rows (Splink+Trigram): **3,837**

## Method Distribution
| Method | Count | Percent | Avg confidence |
|---|---:|---:|---:|
| NAME_CITY_STATE_EXACT | 3,649 | 29.5% | 0.950 |
| NAME_AGGRESSIVE_STATE | 2,580 | 20.9% | 0.750 |
| FUZZY_SPLINK_ADAPTIVE | 2,158 | 17.5% | 0.982 |
| NAME_STATE_EXACT | 1,876 | 15.2% | 0.900 |
| FUZZY_TRIGRAM | 1,679 | 13.6% | 0.754 |
| NAME_AGGRESSIVE_STATE_CITY_RESOLVED | 354 | 2.9% | 0.750 |
| NAME_AGGRESSIVE_STATE_SPLINK_RESOLVED | 59 | 0.5% | 0.799 |

## Method Samples (5 each)
### NAME_CITY_STATE_EXACT
- `1792341` -> `0f1b51d5e7e3b4f1` | conf=0.950 | The Anthem Companies of California, Inc. => Anthem Blue Cross 
- `1644794` -> `61b6c51938b294ee` | conf=0.950 | American Pacific Fine Chemicals => Ampac Fine Chemicals
- `1679286` -> `d9f6268913eabdc3` | conf=0.950 | St. Christopher's Inc. => St. Christopher's, Inc.
- `1926530` -> `5ae372fa4e4918d3` | conf=0.950 | Gradney Management, Inc. => AVIS RENT A CAR
- `1392484` -> `27313cb5b6b989d6` | conf=0.950 | Burlington House => Burlington House

### NAME_AGGRESSIVE_STATE
- `1485335` -> `9bf33d0f41abf55e` | conf=0.750 | Rockledge NH, LLC => Rockledge Health and Rehabilitation
- `1723590` -> `3b52709246fe36e4` | conf=0.750 | A & A Maintenance Enterprise, Inc. => A & A Maintenance Enterprise
- `1469104` -> `78ce689fdb60e303` | conf=0.750 | Dalton Maintenance, Inc. => Dalton Maintenance Inc.
- `1410851` -> `6a383f90e16af7f5` | conf=0.750 | Vulcan Materials Company => Vulcan Materials Company LP
- `1895363` -> `ea369a34022e192c` | conf=0.750 | Indiana Earth, Inc. => Indiana Earth, Inc.

### FUZZY_SPLINK_ADAPTIVE
- `1777548` -> `98fbd0f75df9a6da` | conf=0.992 | MO EMP LLC => Crestwood Health Care Center LLC
- `1909646` -> `c229a1c8102b44b1` | conf=1.000 | Specialized Pavement Marking, Inc. => Specialized Pavement Markings, LLC. 
- `1602362` -> `19645db03e4d95a9` | conf=0.775 | Ellis Hospital Bellevue Care Center => Ellis Hospital and Bellevue Woman's Center
- `1491608` -> `bc3c6814615a40d1` | conf=1.000 | Harley-Davidson, Inc. => Harley-Davidson Motor Company
- `1411883` -> `c5fb988e146179aa` | conf=1.000 | City of Philadelphia => Philadelphia Department of Prisons

### NAME_STATE_EXACT
- `1472522` -> `f6de7aa750dd870e` | conf=0.900 | Lake County Cartage, Inc. => LAKE COUNTY CARTAGE
- `1743826` -> `09539a258b3ad4a4` | conf=0.900 | Healthcare Services Group, Inc. => Healthcare Services Group, Inc.
- `1652402` -> `b902e200219129d0` | conf=0.900 | Jacobson Excavation, LLC => Jacobson Excavation
- `1727272` -> `fba0304df1e93a0e` | conf=0.900 | ACH Food Companies, Inc => ACH Foods Inc.
- `1589888` -> `3dc3e9c6c3ebac55` | conf=0.900 | Chugach Managment Service => CHUGACH INDUSTRIES

### FUZZY_TRIGRAM
- `1390793` -> `1fb49a2bd7f1abe7` | conf=0.706 | Ventura Convalescent Hospital => Vernon Convalescent Hospital
- `1635128` -> `20dfdaddfb9ecc5a` | conf=0.879 | Sierra Landscape Development => SIERRA LANDSCAPE DEVELOPMENT (Landscape)
- `1899550` -> `a4c5f1a54a52c459` | conf=0.708 | Cannon Construction, Inc => D&D Construction Inc
- `1874128` -> `945566f47e0f0a9c` | conf=0.736 | 702 South Kings Ave Ops/CMC II, LLC/Consulate => Heritage Park Healthcare and Rehabilitation Center
- `1962523` -> `a54bdacd7a86c42e` | conf=0.739 | R-Construction, Inc. => TEF CONSTRUCTION INC

### NAME_AGGRESSIVE_STATE_CITY_RESOLVED
- `1874747` -> `cbb9f6922c67afdb` | conf=0.750 | KBO, Inc. => Klosterman Baking Company
- `1392612` -> `55cd09658b2590dd` | conf=0.750 | Fresh Cut Lawn Care, Inc. => Fresh Cut Lawn Care, Inc
- `1574127` -> `af9403632a263582` | conf=0.750 | Kauai Veterans Express => Kauai Veterans Express Co
- `1662922` -> `401373ff9fa2081b` | conf=0.750 | Campobello Construction Co., Inc. => Campobello Construction
- `1927287` -> `b19ed3eaf3a48943` | conf=0.750 | Mississippi Action for Progress, Inc. => Mississippi Action for Progress

### NAME_AGGRESSIVE_STATE_SPLINK_RESOLVED
- `1553623` -> `67b80c5d18232ef3` | conf=0.801 | Ameriguard Security Services Inc. => Ameriguard Security Services Co
- `1957789` -> `0f6f48ab0aaf55ef` | conf=0.801 | SIMS Crane & Equipment Co => SIMS CRANE & EQUIPMENT CO.
- `1972966` -> `1b2cddd4bda99f89` | conf=0.801 | Amentum Services, Inc. => Amentum Services
- `1749447` -> `360269205ba4cfc4` | conf=0.801 | Guardian Eldercare LLC => Guardian Elder Care
- `1898118` -> `eaeb9e3bba993c3c` | conf=0.801 | Aramark Sports & Entertainment Svcs, LLC => ARAMARK Sports & Entertainment

## Fuzzy Similarity Distribution
| Band | Count | Percent of fuzzy |
|---|---:|---:|
| <0.80 | 1,364 | 35.5% |
| 0.80-0.84 | 1,142 | 29.8% |
| 0.85-0.89 | 608 | 15.8% |
| 0.90-0.94 | 277 | 7.2% |
| 0.95-1.00 | 194 | 5.1% |

### Fuzzy Band Samples (3 each)
#### <0.80
- sim=0.771 | `1405475` -> `dc73b98e2033ba83` | San Diego Unified School District => San Juan Unified School District
- sim=0.769 | `1380884` -> `c5c687ab3e9d44e1` | CSX Transportation, Inc. => CRL Transportation, Inc.
- sim=0.771 | `1617017` -> `f4fd48b14cb038fe` | Visiting Nurse Association of Long Island => Visiting Nurse Association of Staten Island 
#### 0.80-0.84
- sim=0.833 | `1728763` -> `1f4713daadb936fa` | Jimenez Construction, Inc => JIC Construction, Inc. dba Sterling Pacific
- sim=0.807 | `1398625` -> `626c39f3bc04bb70` | Manhattenview Operations LLC => Manhattan View Health Care
- sim=0.815 | `1348563` -> `b03cba1a7513d86a` | California Culinary Academy => California Academy of Sciences
#### 0.85-0.89
- sim=0.857 | `1624225` -> `2457a36c96136d75` | Kilgore Industries, LP => Nailor Industries
- sim=0.867 | `1698625` -> `d5ce4c8dc8519bea` | Cuyahoga Community College => Aramark @ Cuyahoga Community College
- sim=0.862 | `1702244` -> `412c8a780eb0e337` | Sarasota Doctors Hospital, Inc./Hospital Corp => Doctor's Hospital of Sarasota, HCA
#### 0.90-0.94
- sim=0.939 | `1632985` -> `84edf423edbb407b` | Watkins Security Agency => Watkins Security Agency of DC Inc
- sim=0.926 | `1551824` -> `1f80ed9f3d093f6e` | Chicago Transit Authority (CTA) => Chicago Transit Authority
- sim=0.902 | `1821195` -> `159aa123eee11b1c` | Gryphon Technologies L.C., LLC => Gryphon Technologies, LC
#### 0.95-1.00
- sim=0.981 | `1433785` -> `fe90352893638c5b` | Governor's State University => Governors State University
- sim=0.979 | `1956304` -> `8a7d93031c987eca` | Marriott Hotel Services, Inc. => Marriot Marquis Houston
- sim=0.964 | `1743652` -> `92705c3ed7b5ccad` | Dana-Farber Cancer Institue => Dana Farber Cancer Institute

## EIN Checks
- WHD source has EIN column: **False**
- WHD records with EIN present: **0**
- Active WHD matches with method `EIN_EXACT`: **0**
- Active WHD matches where source record has EIN present: **0**
- Potential EIN conflicts found (sampled): **0**

## Potential Deterministic Gaps (Exact Name+State but No Active Match)
- Found examples: **20** (limited to top 20)
- WHD `1388080` (OH) Ford Motor Company -> F7 `6d410d067452df71` Ford Motor Company
- WHD `1388080` (OH) Ford Motor Company -> F7 `b70cdfb28764260e` Ford Motor Company
- WHD `1388080` (OH) Ford Motor Company -> F7 `5322159d196f2a1e` Ford Motor Company
- WHD `1388080` (OH) Ford Motor Company -> F7 `31b1e6a6b0595c71` Ford Motor Company
- WHD `1388080` (OH) Ford Motor Company -> F7 `da8a02cca1348d22` Ford Motor Company
- WHD `1388080` (OH) Ford Motor Company -> F7 `40e74f694fd9c736` Ford Motor Company
- WHD `1646102` (OH) CenturyLink -> F7 `649f4793be9731fd` Centurylink
- WHD `1646102` (OH) CenturyLink -> F7 `722fe672fb310dd6` CenturyLink
- WHD `1513901` (RI) Subway -> F7 `90f9fd551894c573` Subway
- WHD `1513901` (RI) Subway -> F7 `c1192b4d6fc944aa` Subway
- WHD `1501877` (RI) CVS/Pharmacy -> F7 `2cbaa1b28400683f` CVS/Pharmacy
- WHD `1501877` (RI) CVS/Pharmacy -> F7 `54212df1f4ee1ca2` CVS Pharmacy
- WHD `1806551` (NY) Hertz Corporation -> F7 `ab6ac2b2ec75d457` Hertz Corporation
- WHD `1806551` (NY) Hertz Corporation -> F7 `c4949f65e0e78f93` Hertz Corporation
- WHD `1806551` (NY) Hertz Corporation -> F7 `d9d039281d4ba818` Hertz Corporation 
- WHD `1861479` (GA) Greif Packaging LLC -> F7 `12fd4d3d430a316c` Greif Packaging, LLC
- WHD `1912395` (OH) American Electric Power -> F7 `a75f5674bfbeb51d` American Electric Power
- WHD `1912395` (OH) American Electric Power -> F7 `c6777fcc070e4ab2` American Electric Power
- WHD `1912395` (OH) American Electric Power -> F7 `c736644c7b5a3e4c` American Electric Power
- WHD `1912395` (OH) American Electric Power -> F7 `cf90039f1a5c9693` American Electric Power

## Recommended Actions
- Expand deterministic pass to capture exact name+state WHD rows without active matches.
- If EIN matching is intended, wire WHD EINs into a crosswalk table; `f7_employers_deduped` has no EIN field.
- Keep duplicate-source resolution in place to prevent one case_id from staying linked to multiple targets.
