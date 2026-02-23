# I14 SAM Matching Quality Audit

## Summary
- Active SAM matches: **17,687**
- Match methods observed: **7**
- Fuzzy rows (Splink+Trigram): **5,953**

## Method Distribution
| Method | Count | Percent | Avg confidence | Quality |
|---|---:|---:|---:|---|
| NAME_CITY_STATE_EXACT | 5,456 | 30.8% | 0.950 | good |
| NAME_AGGRESSIVE_STATE | 3,905 | 22.1% | 0.750 | acceptable |
| FUZZY_TRIGRAM | 3,748 | 21.2% | 0.750 | concerning |
| FUZZY_SPLINK_ADAPTIVE | 2,205 | 12.5% | 0.976 | concerning |
| NAME_STATE_EXACT | 1,794 | 10.1% | 0.900 | good |
| NAME_AGGRESSIVE_STATE_CITY_RESOLVED | 490 | 2.8% | 0.750 | acceptable |
| NAME_AGGRESSIVE_STATE_SPLINK_RESOLVED | 89 | 0.5% | 0.793 | acceptable |

## Method Samples (5 each)
### NAME_CITY_STATE_EXACT
- `FJB7BZNN98P1` -> `1676c81701643822` | conf=0.950 | DOOLITTLE CONSTRUCTION LLC => Doolittle Construction LLC
- `L41EVAMDE381` -> `ac316418d682ddab` | conf=0.950 | BELLEVILLE TOWNSHIP HIGH SCHOOL DISTRICT 201 => Belleville Township High School District 201
- `H8FFNA7B4H22` -> `5931a17e367cc25d` | conf=0.950 | MERLO PLUMBING COMPANY, INC. => MERLO PLUMBING COMPANY, INC.
- `TKCEKVNRC778` -> `6d0bfaf4f99d9697` | conf=0.950 | TATE & HILL, INC => Tate & Hill, Inc.
- `RULFPWW1CG99` -> `f3d72c75f1a3e399` | conf=0.950 | CHEYENNE LIGHT, FUEL AND POWER COMPANY => Cheyenne Light Fuel and Power Company

### NAME_AGGRESSIVE_STATE
- `N9MQP5JDLGX5` -> `44f84f8d7622b30d` | conf=0.750 | WAUKESHA FOUNDRY INC => Waukesha Foundry
- `L9V6HJAH4Z67` -> `97fa043b09ffd91f` | conf=0.750 | WAYNE COUNTY COMMUNITY SERVICES ORGANIZATION, INC => Wayne County Community Service Organization, Inc.
- `T6BDZJKMBY91` -> `5190b71d6ecf7bbb` | conf=0.750 | ENTERPRISE MASONRY CORPORATION => Enterprise Masonry Corp.
- `KBWEFMLA7ZM3` -> `cd6c7d83332908d7` | conf=0.750 | GOLDEN STATE WATER CO => Golden State Water
- `N9NBKML96N41` -> `14ae033ec4ded014` | conf=0.750 | MAXIMUM SECURITY PRODUCTS CORP => Maximum Security Products

### FUZZY_TRIGRAM
- `XDANFGWRCB36` -> `9c9e1cf6442520d1` | conf=0.710 | KOHL BUILDING SERVICES, INC => GMI Building Services Inc.
- `FNZAJFPL59L6` -> `63663e8c433a3d19` | conf=0.806 | COLMA FIRE PROTECTION DISTRICT => Fire Protection District
- `CTMWVVNTPBV5` -> `2b2435c57a121f44` | conf=0.750 | ARCO CONSTRUCTION, INC => AP Construction, Inc.
- `JN7XMMMF2DL3` -> `5514d1c240f634f2` | conf=0.750 | MAC MANUFACTURING, INC => BUD MANUFACTURING, INC.
- `FYKMCEGQN7Z8` -> `d18e671004958cfc` | conf=0.818 | D & A CONTRACTORS, INC. => A & P Contractors Inc.

### FUZZY_SPLINK_ADAPTIVE
- `UG8ACQ3V1EH5` -> `59f819f017373a55` | conf=0.892 | INDEPENDENT SCHOOL DISTRICT 271 => Independent School District #16
- `HU3PM93SB6L9` -> `9a765953e9a8278d` | conf=0.992 | JWS HEALTH CONSULTANTS, INC. => Health Consultants
- `HREXMUMCERH9` -> `0c9cd9508e57fa5f` | conf=0.998 | TROY COMMUNICATIONS => Valley Communications Inc
- `LC7JNLALHEF1` -> `524111bde8cd0e3d` | conf=1.000 | AE7 PITTSBURGH LLC => AEG Management Pittsburgh, LLC
- `SGK9WCQYL9L5` -> `6662ced83ad74118` | conf=1.000 | CARE CENTER (LANECO), INC. => Care Center (Lane Co) Inc.

### NAME_STATE_EXACT
- `PMYLAS13RLK9` -> `9a34680f5c5f10f7` | conf=0.900 | SYNERGY LOGISTICS SERVICES, LLC => Synergy Logistics Services, LLC
- `GUZ6SKC17JM3` -> `e6acfdf3aa4df2ca` | conf=0.900 | G.C. ZARNAS & CO., INC.(NE) => G.C. Zarnas & Co., Inc. (NE)
- `MXFEK67FT9K5` -> `4e5f2e31c952505f` | conf=0.900 | THE SHERWIN-WILLIAMS COMPANY => The Sherwin-Williams Company
- `HCB4H2HQF2R5` -> `6848e7e4507a1684` | conf=0.900 | DCD CONTRACTING, INC => DCD Contracting Inc.
- `KQU9YT4TD878` -> `965cb4dd8c4f6215` | conf=0.900 | CALIFORNIA STATE UNIVERSITY => California State University

### NAME_AGGRESSIVE_STATE_CITY_RESOLVED
- `MM76KBAN1J35` -> `5056cb1cd0a85ce5` | conf=0.750 | AQUA-AEROBIC SYSTEMS INC => Aqua-Aerobic Systems
- `TAKSX2K3GRY8` -> `05a5a390820bfe7a` | conf=0.750 | CORNERSTONE CHEMICAL COMPANY, LLC => Cornerstone Chemical Company
- `M8CAG8UV6174` -> `6261c17ac721c0f8` | conf=0.750 | MARRIOTT HOTEL SERVICES, LLC => Marriott Hotel Services, Inc.
- `RYF6GH258MT3` -> `15b906a3c652e245` | conf=0.750 | THE GRIEVE CORPORATION => Grieve Corporation
- `EVP4KM37YU23` -> `f00f94e0d549561e` | conf=0.750 | CLEVELAND-CLIFFS INC. => CLEVELAND-CLIFFS INCORPORATED

### NAME_AGGRESSIVE_STATE_SPLINK_RESOLVED
- `HCK6RJBKLC53` -> `4272b8e41719ae37` | conf=0.801 | RHA HEALTH SERVICES, INC. => RHA Health Services
- `RBL4PXG4C1G4` -> `f7b5c97a85605a76` | conf=0.801 | MCI SALES & SERVICE INC => MCI SALES & SERVICE
- `JJJVSJU2HFX1` -> `46bfefa50a2ef673` | conf=0.801 | SIEVERT ELECTRIC SERVICE AND SALES COMPANY => Sievert Electric Service and Sales Co.
- `W3VDNSZ526R9` -> `f2a52d03b75f4f66` | conf=0.801 | A-TECH CONCRETE COMPANY INC => A-TECH CONCRETE COMPANY INCORPORATED
- `U1KDLT1Z61V3` -> `22f4c71a665f2b6a` | conf=0.801 | BROAD MOUNTAIN HEALTH & REHABILITATION CENTER, LLC => Broad Mountain Health & Rehabilitation Center

## Fuzzy Similarity Distribution
| Band | Count | Percent of fuzzy |
|---|---:|---:|
| <0.80 | 3,165 | 53.2% |
| 0.80-0.84 | 1,334 | 22.4% |
| 0.85-0.89 | 631 | 10.6% |
| 0.90-0.94 | 347 | 5.8% |
| 0.95-1.00 | 167 | 2.8% |

### Fuzzy Band Samples (3 each)
#### <0.80
- sim=0.792 | `GL58EKMMEK43` -> `9d945996cffcaa48` | ABBS VISION SYSTEMS, INC => Vision Systems, Inc.
- sim=0.72 | `FPJTHSZUVLS8` -> `dadf2c84086fb24b` | GN CONSTRUCTION CO INC => COMBS CONSTRUCTION CO., INC.
- sim=0.706 | `MF4SCJGHJ921` -> `489233eb74a0392f` | S&L ELECTRICAL SERVICES LLC => Premier Electrical Services LLC
#### 0.80-0.84
- sim=0.833 | `FRNNCCF87WL5` -> `48e3cbf628ef64d2` | FERRELLGAS, L.P => Ferrellgas, Inc.
- sim=0.824 | `X86HD5LNKHV4` -> `65304759e583eefd` | CARROLL COUNTY => Carroll County Board
- sim=0.826 | `TPJKP6CRWA28` -> `6a275156511533ba` | MILLIKIN UNIVERSITY => Aramark / Millikin University
#### 0.85-0.89
- sim=0.885 | `NCTZMKV6EHG2` -> `6e5cf83ff88cddee` | CATHOLIC HEALTH CARE SYSTEM => Catholic Health System
- sim=0.889 | `QVYLGUH2FQB1` -> `9de97179dadd03eb` | HOUSTON HOUSING & REDEVELOPMENT AUTHORITY => HOUSING & REDEVELOPMENT AUTHORITY
- sim=0.867 | `Y7DHDRQELL88` -> `5eb1ba1f36a8b296` | MUNICIPAL AUTHORITY OF THE TOWNSHIP OF WASHINGTON => Washington Township Municipal Authority 
#### 0.90-0.94
- sim=0.909 | `KZQNB4LKN6C8` -> `9783865af4fbaba5` | BAYSHORE REGIONAL SEWERAGE AUT => Bayshore Regional Sewerage Authority
- sim=0.906 | `KJ1JJ9WJLUS6` -> `339508890fecf5ea` | PASSAVANT MEMORIAL HOMES VIII => Passavant Memorial Homes
- sim=0.923 | `WMTFKGSFHSZ9` -> `ea651d9fa49d3900` | SOUTHWEST GREENSBURG BOROUGH => South Greensburg Borough
#### 0.95-1.00
- sim=1.0 | `KJASNBMQGLG3` -> `698fc455e301a107` | WANAQUE BOROUGH OF => Borough of Wanaque
- sim=0.978 | `YJ1VB6MNZ6T5` -> `e4ba626dd0c0baed` | HOLLAND CENTRAL SCHOOL => Holland Central Schools
- sim=0.963 | `YFSBYGBG51N3` -> `072bca8f0ef70660` | PAYSON COMMUNITY UNIT SCHOOL DISTRICT 1 => Payson Community Unit School District No. 1

## Potential Deterministic Gaps (Exact Name+State but No Active Match)
- Found examples: **0** (limited to top 20)

## Recommended Actions
- Prioritize review of fuzzy matches below 0.85 similarity.
- Backfill deterministic exact-name+state pass for unmatched SAM examples.
- Keep cross-method dedupe enabled so one SAM source_id maps to exactly one active target.
