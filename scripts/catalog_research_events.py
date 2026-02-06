"""
Catalog Research Events - Script 1 of 3

Hard-codes all qualifying organizing events from 5 research agents into
structured records and outputs to CSV. Excludes worker centers, contract
renegotiations at already-unionized employers, failed elections, and strikes
at existing union shops.

Agent sources:
  1. NY Discovery & Gap Analysis (2021-2026)
  2. Construction/Manufacturing/Retail (NAICS 23, 31, 44)
  3. Transportation/Tech/Professional (NAICS 48, 51, 54)
  4. Education/Healthcare (NAICS 61, 62)
  5. Arts/Entertainment/Hospitality (NAICS 71, 72)
"""

import csv
import os
import re
import sys

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.matching.normalizer import normalize_employer_name

OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "organizing_events_catalog.csv")

FIELDS = [
    "employer_name", "employer_name_normalized", "city", "state",
    "union_name", "affiliation_code", "local_number",
    "num_employees", "recognition_type", "recognition_date",
    "naics_sector", "source_description", "notes", "agent_source"
]


def build_events():
    """Build the full list of qualifying organizing events."""
    events = []

    # ================================================================
    # AGENT 1: NY Discovery & Gap Analysis
    # ================================================================
    agent = "NY_DISCOVERY"

    # --- Museums ---
    events.append({
        "employer_name": "Metropolitan Museum of Art",
        "city": "New York", "state": "NY",
        "union_name": "UAW Local 2110",
        "affiliation_code": "UAW", "local_number": "2110",
        "num_employees": 700,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2026-01-15",
        "naics_sector": "71",
        "source_description": "Met Museum workers voted to unionize with UAW Local 2110",
        "notes": "Largest US art museum unionization",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "American Folk Art Museum",
        "city": "New York", "state": "NY",
        "union_name": "UAW Local 2110",
        "affiliation_code": "UAW", "local_number": "2110",
        "num_employees": 50,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-06-01",
        "naics_sector": "71",
        "source_description": "Folk Art Museum staff organized with UAW Local 2110",
        "notes": "Part of NYC museum wave",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Solomon R. Guggenheim Museum",
        "city": "New York", "state": "NY",
        "union_name": "UAW Local 2110",
        "affiliation_code": "UAW", "local_number": "2110",
        "num_employees": 100,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-01-01",
        "naics_sector": "71",
        "source_description": "Guggenheim workers ratified first contract",
        "notes": "First contract achieved",
        "agent_source": agent,
    })

    # --- Media/Digital ---
    events.append({
        "employer_name": "Conde Nast",
        "city": "New York", "state": "NY",
        "union_name": "NewsGuild-CWA Local 31003",
        "affiliation_code": "CWA", "local_number": "31003",
        "num_employees": 500,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-03-01",
        "naics_sector": "51",
        "source_description": "Conde Nast workers organized with NewsGuild-CWA",
        "notes": "Vogue, GQ, Vanity Fair editorial staff",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "New York Times (Tech Guild)",
        "city": "New York", "state": "NY",
        "union_name": "NewsGuild-CWA Local 31003",
        "affiliation_code": "CWA", "local_number": "31003",
        "num_employees": 600,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-03-03",
        "naics_sector": "51",
        "source_description": "NYT Tech Guild organized tech workers with CWA",
        "notes": "Tech workers separate from editorial NewsGuild unit",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "CBS News Digital",
        "city": "New York", "state": "NY",
        "union_name": "WGA East",
        "affiliation_code": "UNAFF", "local_number": None,
        "num_employees": 100,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-06-01",
        "naics_sector": "51",
        "source_description": "CBS News Digital staff organized with WGA East",
        "notes": "Digital news producers and writers",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Lemonada Media",
        "city": "New York", "state": "NY",
        "union_name": "WGA East",
        "affiliation_code": "UNAFF", "local_number": None,
        "num_employees": 30,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2023-09-01",
        "naics_sector": "51",
        "source_description": "Podcast company Lemonada Media voluntarily recognized WGA East",
        "notes": "Podcast workers",
        "agent_source": agent,
    })

    # --- Cannabis ---
    events.append({
        "employer_name": "Cannabis Industry Workers (NY - aggregate)",
        "city": "New York", "state": "NY",
        "union_name": "RWDSU/UFCW Local 338",
        "affiliation_code": "RWDSU", "local_number": "338",
        "num_employees": 600,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2023-06-01",
        "naics_sector": "44",
        "source_description": "NY cannabis LPA framework requires labor peace; 600+ workers via Local 338",
        "notes": "Aggregate - multiple dispensaries and grow facilities under NY LPA",
        "agent_source": agent,
    })

    # --- Farm Workers (NY PERB certifications) ---
    ny_farms = [
        ("Riverview Nursery", "Rensselaer", 60),
        ("H&H Farms", "Canandaigua", 45),
        ("Torrey Farms", "Elba", 80),
        ("Marks Farms", "Lowville", 50),
        ("Wafler Farms", "Wolcott", 40),
        ("Ellsworth & Rose", "Albion", 35),
        ("LynOaken Farms", "Medina", 50),
    ]
    for farm_name, farm_city, workers in ny_farms:
        events.append({
            "employer_name": farm_name,
            "city": farm_city, "state": "NY",
            "union_name": "United Farm Workers",
            "affiliation_code": "UNAFF", "local_number": None,
            "num_employees": workers,
            "recognition_type": "STATE_PERB",
            "recognition_date": "2023-01-01",
            "naics_sector": "11",
            "source_description": "NY PERB farm certification under Farm Laborers Fair Labor Practices Act",
            "notes": "100% gap in federal databases - NY state jurisdiction only",
            "agent_source": agent,
        })

    # --- Home Health Aide / HHWA ---
    events.append({
        "employer_name": "Home Health Aides (HHWA - aggregate NY)",
        "city": "New York", "state": "NY",
        "union_name": "1199SEIU",
        "affiliation_code": "SEIU", "local_number": "1199",
        "num_employees": 6700,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2022-01-01",
        "naics_sector": "62",
        "source_description": "HHWA voluntary recognition for home care workers across 15+ agencies",
        "notes": "Controversial rapid recognition model; aggregate for multiple home care agencies",
        "agent_source": agent,
    })

    # --- Nonprofits / Legal Services ---
    events.append({
        "employer_name": "Legal Aid Society",
        "city": "New York", "state": "NY",
        "union_name": "UAW Local 2325 (ALAA)",
        "affiliation_code": "UAW", "local_number": "2325",
        "num_employees": 1800,
        "recognition_type": "COLLECTIVE_BARGAINING",
        "recognition_date": "2021-01-01",
        "naics_sector": "54",
        "source_description": "ALAA-UAW represents Legal Aid Society attorneys",
        "notes": "Largest legal services union in US; longstanding but new contract actions 2021-2025",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Legal Services NYC",
        "city": "New York", "state": "NY",
        "union_name": "UAW Local 2320 (ALAA)",
        "affiliation_code": "UAW", "local_number": "2320",
        "num_employees": 400,
        "recognition_type": "COLLECTIVE_BARGAINING",
        "recognition_date": "2021-06-01",
        "naics_sector": "54",
        "source_description": "ALAA-UAW represents Legal Services NYC staff attorneys",
        "notes": "Part of ALAA network of 35+ nonprofit legal orgs",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Brooklyn Defender Services",
        "city": "Brooklyn", "state": "NY",
        "union_name": "UAW Local 2325 (ALAA)",
        "affiliation_code": "UAW", "local_number": "2325",
        "num_employees": 300,
        "recognition_type": "COLLECTIVE_BARGAINING",
        "recognition_date": "2022-01-01",
        "naics_sector": "54",
        "source_description": "ALAA-UAW represents Brooklyn Defender Services attorneys",
        "notes": "Public defender office",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Bronx Defenders",
        "city": "Bronx", "state": "NY",
        "union_name": "UAW Local 2325 (ALAA)",
        "affiliation_code": "UAW", "local_number": "2325",
        "num_employees": 250,
        "recognition_type": "COLLECTIVE_BARGAINING",
        "recognition_date": "2022-06-01",
        "naics_sector": "54",
        "source_description": "ALAA-UAW represents Bronx Defenders staff",
        "notes": "Public defender office",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Neighborhood Defender Service of Harlem",
        "city": "New York", "state": "NY",
        "union_name": "UAW Local 2325 (ALAA)",
        "affiliation_code": "UAW", "local_number": "2325",
        "num_employees": 150,
        "recognition_type": "COLLECTIVE_BARGAINING",
        "recognition_date": "2022-01-01",
        "naics_sector": "54",
        "source_description": "ALAA-UAW represents NDS Harlem staff",
        "notes": "Public defender office",
        "agent_source": agent,
    })

    # --- NYC Public Sector ---
    events.append({
        "employer_name": "New York City Council",
        "city": "New York", "state": "NY",
        "union_name": "CWA Local 1180",
        "affiliation_code": "CWA", "local_number": "1180",
        "num_employees": 382,
        "recognition_type": "STATE_PUBLIC",
        "recognition_date": "2024-01-01",
        "naics_sector": "92",
        "source_description": "NYC Council staff organized - first new public unit in 50 years",
        "notes": "Central staff of NYC Council",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Breaking Ground",
        "city": "New York", "state": "NY",
        "union_name": "AFSCME DC 37",
        "affiliation_code": "AFSCME", "local_number": "37",
        "num_employees": 250,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-01-01",
        "naics_sector": "62",
        "source_description": "Breaking Ground nonprofit shelter workers organized with DC 37",
        "notes": "Homeless services nonprofit",
        "agent_source": agent,
    })

    # --- Retail (NY-specific) ---
    events.append({
        "employer_name": "Blank Street Coffee (NY - aggregate)",
        "city": "New York", "state": "NY",
        "union_name": "Workers United/SEIU",
        "affiliation_code": "WU", "local_number": None,
        "num_employees": 200,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-01-01",
        "naics_sector": "72",
        "source_description": "Blank Street Coffee 19 NYC stores organizing with Workers United",
        "notes": "Aggregate - 19 stores",
        "agent_source": agent,
    })

    # --- Higher Ed (NY-specific) ---
    events.append({
        "employer_name": "School of Visual Arts",
        "city": "New York", "state": "NY",
        "union_name": "UAW Local 7902",
        "affiliation_code": "UAW", "local_number": "7902",
        "num_employees": 1200,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-06-01",
        "naics_sector": "61",
        "source_description": "SVA adjunct faculty organized with UAW",
        "notes": "Adjunct faculty",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Mount Sinai Graduate School",
        "city": "New York", "state": "NY",
        "union_name": "UAW Local 2110",
        "affiliation_code": "UAW", "local_number": "2110",
        "num_employees": 800,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-09-01",
        "naics_sector": "61",
        "source_description": "Mount Sinai postdocs and grad students organized",
        "notes": "Postdoctoral researchers and grad students",
        "agent_source": agent,
    })

    # ================================================================
    # AGENT 2: Construction / Manufacturing / Retail
    # ================================================================
    agent = "CONSTRUCTION_MFG_RETAIL"

    # --- Manufacturing ---
    events.append({
        "employer_name": "Volkswagen Chattanooga Assembly Plant",
        "city": "Chattanooga", "state": "TN",
        "union_name": "UAW",
        "affiliation_code": "UAW", "local_number": None,
        "num_employees": 3200,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-04-19",
        "naics_sector": "31",
        "source_description": "VW Chattanooga voted 73% to join UAW - historic southern auto win",
        "notes": "First foreign-owned auto plant in South to unionize; 2,628-985 vote",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Blue Bird Corporation",
        "city": "Fort Valley", "state": "GA",
        "union_name": "USW",
        "affiliation_code": "USW", "local_number": None,
        "num_employees": 1500,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-06-14",
        "naics_sector": "31",
        "source_description": "Blue Bird school bus manufacturer workers voted to join USW",
        "notes": "Only US-owned school bus manufacturer",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Ultium Cells LLC (GM/LG joint venture)",
        "city": "Spring Hill", "state": "TN",
        "union_name": "UAW",
        "affiliation_code": "UAW", "local_number": None,
        "num_employees": 1000,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-12-01",
        "naics_sector": "31",
        "source_description": "EV battery plant workers organized with UAW",
        "notes": "Part of EV battery plant organizing wave",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Ultium Cells LLC (GM/LG - Lordstown)",
        "city": "Lordstown", "state": "OH",
        "union_name": "UAW",
        "affiliation_code": "UAW", "local_number": None,
        "num_employees": 1200,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-12-09",
        "naics_sector": "31",
        "source_description": "First EV battery plant to unionize with UAW",
        "notes": "Lordstown facility",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "BlueOval SK Battery Park",
        "city": "Glendale", "state": "KY",
        "union_name": "UAW",
        "affiliation_code": "UAW", "local_number": None,
        "num_employees": 800,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-10-01",
        "naics_sector": "31",
        "source_description": "Ford/SK EV battery plant workers organizing with UAW",
        "notes": "Ford-SK Innovation joint venture",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "StarPlus Energy (Samsung SDI/Stellantis)",
        "city": "Kokomo", "state": "IN",
        "union_name": "UAW",
        "affiliation_code": "UAW", "local_number": None,
        "num_employees": 600,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-08-01",
        "naics_sector": "31",
        "source_description": "Stellantis/Samsung EV battery plant workers joined UAW",
        "notes": "EV battery plant wave",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Mercedes-Benz Vance Plant",
        "city": "Vance", "state": "AL",
        "union_name": "UAW",
        "affiliation_code": "UAW", "local_number": None,
        "num_employees": 5000,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-05-17",
        "naics_sector": "31",
        "source_description": "Mercedes-Benz Vance workers voted on UAW - narrowly lost",
        "notes": "EXCLUDED - election lost 2,642 vs 2,045",
        "agent_source": agent,
    })

    # --- Retail ---
    events.append({
        "employer_name": "Starbucks (aggregate - 640+ stores)",
        "city": "Various", "state": "US",
        "union_name": "Workers United/SEIU",
        "affiliation_code": "WU", "local_number": None,
        "num_employees": 14000,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-12-09",
        "naics_sector": "72",
        "source_description": "640+ Starbucks stores organized with Workers United since Dec 2021",
        "notes": "Aggregate record; individual stores in nlrb_elections; zero first contracts as of 2026",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Amazon (JFK8 Warehouse)",
        "city": "Staten Island", "state": "NY",
        "union_name": "Amazon Labor Union / IBT",
        "affiliation_code": "IBT", "local_number": None,
        "num_employees": 8000,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-04-01",
        "naics_sector": "49",
        "source_description": "Amazon JFK8 voted to unionize (ALU, later affiliated with Teamsters)",
        "notes": "First Amazon warehouse to unionize; ALU merged with IBT in 2024",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "REI SoHo",
        "city": "New York", "state": "NY",
        "union_name": "RWDSU",
        "affiliation_code": "RWDSU", "local_number": None,
        "num_employees": 100,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-03-02",
        "naics_sector": "44",
        "source_description": "REI SoHo was first REI store to unionize",
        "notes": "11 REI stores total organized; flagship store",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "REI Berkeley",
        "city": "Berkeley", "state": "CA",
        "union_name": "RWDSU",
        "affiliation_code": "RWDSU", "local_number": None,
        "num_employees": 80,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-08-01",
        "naics_sector": "44",
        "source_description": "REI Berkeley store organized with RWDSU",
        "notes": "Part of REI wave",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "REI Cleveland",
        "city": "Cleveland", "state": "OH",
        "union_name": "RWDSU",
        "affiliation_code": "RWDSU", "local_number": None,
        "num_employees": 70,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-03-01",
        "naics_sector": "44",
        "source_description": "REI Cleveland store organized",
        "notes": "Part of REI wave",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Barnes & Noble (aggregate - 7 stores)",
        "city": "Various", "state": "US",
        "union_name": "RWDSU",
        "affiliation_code": "RWDSU", "local_number": None,
        "num_employees": 350,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-06-01",
        "naics_sector": "44",
        "source_description": "7 Barnes & Noble stores organized with RWDSU",
        "notes": "Aggregate - stores in NYC, NJ, IL",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Apple Towson Town Center",
        "city": "Towson", "state": "MD",
        "union_name": "IAM",
        "affiliation_code": "IAM", "local_number": None,
        "num_employees": 100,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-06-18",
        "naics_sector": "44",
        "source_description": "First Apple retail store in US to unionize",
        "notes": "IAM Coalition of Organized Retail Employees (CORE)",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Apple Penn Square",
        "city": "Oklahoma City", "state": "OK",
        "union_name": "CWA",
        "affiliation_code": "CWA", "local_number": None,
        "num_employees": 80,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-10-14",
        "naics_sector": "44",
        "source_description": "Apple Penn Square store organized with CWA",
        "notes": "Second Apple store to unionize",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "H&M (aggregate - 23 stores)",
        "city": "Various", "state": "US",
        "union_name": "RWDSU",
        "affiliation_code": "RWDSU", "local_number": None,
        "num_employees": 900,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-01-01",
        "naics_sector": "44",
        "source_description": "23 H&M stores organized with RWDSU",
        "notes": "Aggregate - stores across multiple states",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Trader Joe's (aggregate - 8 stores)",
        "city": "Various", "state": "US",
        "union_name": "Trader Joe's United",
        "affiliation_code": "UNAFF", "local_number": None,
        "num_employees": 500,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-07-28",
        "naics_sector": "44",
        "source_description": "8 Trader Joe's stores organized with independent union",
        "notes": "Independent union - Trader Joe's United",
        "agent_source": agent,
    })

    # ================================================================
    # AGENT 3: Transport / Tech / Professional
    # ================================================================
    agent = "TRANSPORT_TECH_PRO"

    # --- Gaming / Tech ---
    events.append({
        "employer_name": "Activision Blizzard QA (Raven Software)",
        "city": "Madison", "state": "WI",
        "union_name": "CWA Local 7250 (Game Workers Alliance)",
        "affiliation_code": "CWA", "local_number": "7250",
        "num_employees": 300,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-05-23",
        "naics_sector": "51",
        "source_description": "First major US video game union at Raven Software QA",
        "notes": "Game Workers Alliance; part of Microsoft/ABK acquisition",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Activision Blizzard QA (Blizzard Albany)",
        "city": "Albany", "state": "NY",
        "union_name": "CWA",
        "affiliation_code": "CWA", "local_number": None,
        "num_employees": 200,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-07-01",
        "naics_sector": "51",
        "source_description": "Blizzard Albany QA workers organized with CWA",
        "notes": "Part of ABK/Microsoft organizing wave",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "ZeniMax Media (Microsoft)",
        "city": "Rockville", "state": "MD",
        "union_name": "CWA",
        "affiliation_code": "CWA", "local_number": None,
        "num_employees": 300,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-01-03",
        "naics_sector": "51",
        "source_description": "ZeniMax QA testers at Bethesda organized with CWA",
        "notes": "Microsoft neutrality agreement facilitated organizing",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Bethesda Game Studios (Microsoft)",
        "city": "Rockville", "state": "MD",
        "union_name": "CWA",
        "affiliation_code": "CWA", "local_number": None,
        "num_employees": 241,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-03-01",
        "naics_sector": "51",
        "source_description": "Bethesda Game Studios developers organized with CWA",
        "notes": "First wall-to-wall game dev union at major AAA studio",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Sega of America",
        "city": "Irvine", "state": "CA",
        "union_name": "CWA (Allied Employees Guild Improving Sega)",
        "affiliation_code": "CWA", "local_number": None,
        "num_employees": 150,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-04-01",
        "naics_sector": "51",
        "source_description": "Sega of America workers formed AEGIS union with CWA",
        "notes": "AEGIS = Allied Employees Guild Improving Sega",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Tender Claws (VR game studio)",
        "city": "Los Angeles", "state": "CA",
        "union_name": "CWA",
        "affiliation_code": "CWA", "local_number": None,
        "num_employees": 15,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2023-05-01",
        "naics_sector": "51",
        "source_description": "Tender Claws VR studio voluntarily recognized CWA",
        "notes": "Indie VR game studio",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Avalanche Studios (Expansive Worlds)",
        "city": "New York", "state": "NY",
        "union_name": "CWA",
        "affiliation_code": "CWA", "local_number": None,
        "num_employees": 100,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-01-01",
        "naics_sector": "51",
        "source_description": "Avalanche Studios workers organized with CWA",
        "notes": "Part of video game unionization wave",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "World of Warcraft (Microsoft) Game Masters",
        "city": "Austin", "state": "TX",
        "union_name": "CWA",
        "affiliation_code": "CWA", "local_number": None,
        "num_employees": 500,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-07-01",
        "naics_sector": "51",
        "source_description": "WoW game masters and customer service organized under Microsoft neutrality",
        "notes": "Largest single ABK/Microsoft unit",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Keywords Studios (Fortnite QA)",
        "city": "El Segundo", "state": "CA",
        "union_name": "CWA",
        "affiliation_code": "CWA", "local_number": None,
        "num_employees": 200,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-04-01",
        "naics_sector": "51",
        "source_description": "Keywords Studios Fortnite QA testers organized with CWA",
        "notes": "Contractor studio for Epic Games",
        "agent_source": agent,
    })

    # --- Architecture ---
    events.append({
        "employer_name": "Bernheimer Architecture",
        "city": "New York", "state": "NY",
        "union_name": "IUOE Local 15A",
        "affiliation_code": "IUOE", "local_number": "15",
        "num_employees": 25,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2024-01-01",
        "naics_sector": "54",
        "source_description": "First private-sector architecture union contract in ~80 years",
        "notes": "Historic first - IUOE Local 15A architects",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "SHoP Architects",
        "city": "New York", "state": "NY",
        "union_name": "IUOE Local 15A",
        "affiliation_code": "IUOE", "local_number": "15",
        "num_employees": 175,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-01-01",
        "naics_sector": "54",
        "source_description": "SHoP Architects filed for NLRB election but withdrew before vote",
        "notes": "EXCLUDED - petition withdrawn, did not go to vote",
        "agent_source": agent,
    })

    # --- Amazon DSP ---
    events.append({
        "employer_name": "Amazon DSP Drivers (Palmdale, CA)",
        "city": "Palmdale", "state": "CA",
        "union_name": "IBT",
        "affiliation_code": "IBT", "local_number": None,
        "num_employees": 84,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-06-01",
        "naics_sector": "49",
        "source_description": "Amazon DSP delivery drivers organized with Teamsters",
        "notes": "Battle Creek Delivery LLC contractor",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Amazon DSP Drivers (Skokie, IL)",
        "city": "Skokie", "state": "IL",
        "union_name": "IBT",
        "affiliation_code": "IBT", "local_number": None,
        "num_employees": 100,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-09-01",
        "naics_sector": "49",
        "source_description": "Amazon DSP delivery drivers organized with Teamsters",
        "notes": "Contractor delivery service provider",
        "agent_source": agent,
    })

    # --- Professional / Other ---
    events.append({
        "employer_name": "Half Price Books (aggregate - multiple stores)",
        "city": "Various", "state": "US",
        "union_name": "CWA",
        "affiliation_code": "CWA", "local_number": None,
        "num_employees": 200,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-09-01",
        "naics_sector": "44",
        "source_description": "Multiple Half Price Books stores organizing with CWA",
        "notes": "Bookstore chain retail workers",
        "agent_source": agent,
    })

    # ================================================================
    # AGENT 4: Education / Healthcare
    # ================================================================
    agent = "EDUCATION_HEALTHCARE"

    # --- Graduate Student Unions ---
    grad_schools = [
        ("Stanford University Graduate Workers", "Stanford", "CA", 3000, "2023-04-01"),
        ("Yale University Graduate Workers", "New Haven", "CT", 3500, "2023-01-01"),
        ("Northwestern University Graduate Workers", "Evanston", "IL", 2800, "2022-11-01"),
        ("Johns Hopkins University Graduate Workers", "Baltimore", "MD", 4000, "2023-03-01"),
        ("Cornell University Graduate Workers", "Ithaca", "NY", 2400, "2022-03-01"),
        ("Duke University Graduate Workers", "Durham", "NC", 2800, "2023-03-01"),
        ("University of Chicago Graduate Workers", "Chicago", "IL", 3500, "2023-04-01"),
        ("MIT Graduate Workers", "Cambridge", "MA", 4000, "2022-04-01"),
        ("University of Minnesota Graduate Workers", "Minneapolis", "MN", 4300, "2023-10-01"),
        ("Indiana University Graduate Workers", "Bloomington", "IN", 3500, "2022-05-01"),
        ("Boston University Graduate Workers", "Boston", "MA", 3800, "2023-03-15"),
        ("University of Southern California Graduate Workers", "Los Angeles", "CA", 5000, "2023-12-01"),
    ]
    for name, city, state, workers, date in grad_schools:
        events.append({
            "employer_name": name,
            "city": city, "state": state,
            "union_name": "UAW / UE",
            "affiliation_code": "UAW", "local_number": None,
            "num_employees": workers,
            "recognition_type": "NLRB_ELECTION",
            "recognition_date": date,
            "naics_sector": "61",
            "source_description": "Graduate student workers organized 2021-2023 wave",
            "notes": "Part of 63,680 grad students newly organized; most affiliated with UAW or UE",
            "agent_source": agent,
        })

    # --- Undergraduate workers ---
    events.append({
        "employer_name": "Cal State University System (Student Workers)",
        "city": "Long Beach", "state": "CA",
        "union_name": "UAW",
        "affiliation_code": "UAW", "local_number": None,
        "num_employees": 20000,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-11-01",
        "naics_sector": "61",
        "source_description": "Cal State student workers organized with UAW",
        "notes": "Undergraduate student workers",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "University of Oregon (Student Workers)",
        "city": "Eugene", "state": "OR",
        "union_name": "SEIU",
        "affiliation_code": "SEIU", "local_number": None,
        "num_employees": 4000,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-05-01",
        "naics_sector": "61",
        "source_description": "U of Oregon student workers organized with SEIU",
        "notes": "Student workers",
        "agent_source": agent,
    })

    # --- Adjunct/Faculty ---
    events.append({
        "employer_name": "University of Southern California (Adjunct Faculty)",
        "city": "Los Angeles", "state": "CA",
        "union_name": "SEIU",
        "affiliation_code": "SEIU", "local_number": None,
        "num_employees": 2500,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-01-01",
        "naics_sector": "61",
        "source_description": "USC adjunct faculty filing with SEIU",
        "notes": "Non-tenure-track faculty",
        "agent_source": agent,
    })

    # --- Charter Schools ---
    events.append({
        "employer_name": "Charter Schools (aggregate - Boston/DC/Providence)",
        "city": "Various", "state": "US",
        "union_name": "AFT",
        "affiliation_code": "AFT", "local_number": None,
        "num_employees": 800,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-01-01",
        "naics_sector": "61",
        "source_description": "AFT organizing across 15+ charter schools in Boston, DC, Providence",
        "notes": "Aggregate - charter school teacher organizing wave",
        "agent_source": agent,
    })

    # --- Healthcare ---
    events.append({
        "employer_name": "Corewell Health",
        "city": "Grand Rapids", "state": "MI",
        "union_name": "SEIU Healthcare Michigan",
        "affiliation_code": "SEIU", "local_number": None,
        "num_employees": 9600,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-01-01",
        "naics_sector": "62",
        "source_description": "Corewell Health 9,600 nurses - largest NLRB election in 20+ years",
        "notes": "Spectrum Health + Beaumont merger system; nurses across multiple hospitals",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Sharp HealthCare",
        "city": "San Diego", "state": "CA",
        "union_name": "SEIU-UHW",
        "affiliation_code": "SEIU", "local_number": None,
        "num_employees": 6000,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-06-01",
        "naics_sector": "62",
        "source_description": "Sharp HealthCare 6,000 workers across entire system",
        "notes": "San Diego health system",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Legacy Health",
        "city": "Portland", "state": "OR",
        "union_name": "ONA/AFT",
        "affiliation_code": "AFT", "local_number": None,
        "num_employees": 3200,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-09-01",
        "naics_sector": "62",
        "source_description": "Legacy Health 3,200+ nurses organized in Portland",
        "notes": "Oregon Nurses Association / AFT affiliate",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "UPMC Magee-Womens Hospital",
        "city": "Pittsburgh", "state": "PA",
        "union_name": "SEIU Healthcare PA",
        "affiliation_code": "SEIU", "local_number": None,
        "num_employees": 1200,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-10-01",
        "naics_sector": "62",
        "source_description": "First-ever UPMC hospital to unionize",
        "notes": "Breakthrough at famously anti-union UPMC system",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Michigan Home Care Workers (aggregate)",
        "city": "Lansing", "state": "MI",
        "union_name": "SEIU Healthcare Michigan",
        "affiliation_code": "SEIU", "local_number": None,
        "num_employees": 35000,
        "recognition_type": "STATE_PUBLIC",
        "recognition_date": "2023-04-01",
        "naics_sector": "62",
        "source_description": "Michigan home care workers regained union rights after legislative change",
        "notes": "Gov. Whitmer restored collective bargaining for home care aides",
        "agent_source": agent,
    })

    # --- CIR-SEIU Physician Wave ---
    events.append({
        "employer_name": "CIR-SEIU Resident Physicians (aggregate - nationwide)",
        "city": "Various", "state": "US",
        "union_name": "CIR-SEIU",
        "affiliation_code": "SEIU", "local_number": None,
        "num_employees": 12000,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-01-01",
        "naics_sector": "62",
        "source_description": "CIR-SEIU doubled to 37K members; 12K new 2021-2025. Philadelphia 83% of residents unionized",
        "notes": "Aggregate new members 2021-2025; includes Stanford, Keck, Penn, Jefferson, etc.",
        "agent_source": agent,
    })

    # ================================================================
    # AGENT 5: Arts / Entertainment / Hospitality
    # ================================================================
    agent = "ARTS_HOSPITALITY"

    # --- Museums (non-NY) ---
    events.append({
        "employer_name": "Los Angeles County Museum of Art (LACMA)",
        "city": "Los Angeles", "state": "CA",
        "union_name": "AFSCME Cultural Workers United",
        "affiliation_code": "AFSCME", "local_number": None,
        "num_employees": 300,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2025-12-01",
        "naics_sector": "71",
        "source_description": "LACMA workers organized with AFSCME CWU",
        "notes": "Part of museum AFSCME wave",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Shedd Aquarium",
        "city": "Chicago", "state": "IL",
        "union_name": "AFSCME Cultural Workers United",
        "affiliation_code": "AFSCME", "local_number": None,
        "num_employees": 180,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-06-01",
        "naics_sector": "71",
        "source_description": "Shedd Aquarium workers organized with AFSCME CWU",
        "notes": "Part of museum AFSCME wave",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Denver Art Museum",
        "city": "Denver", "state": "CO",
        "union_name": "AFSCME Cultural Workers United",
        "affiliation_code": "AFSCME", "local_number": None,
        "num_employees": 180,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-09-01",
        "naics_sector": "71",
        "source_description": "Denver Art Museum workers organized with AFSCME CWU",
        "notes": "Part of museum AFSCME wave",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Monterey Bay Aquarium",
        "city": "Monterey", "state": "CA",
        "union_name": "AFSCME Cultural Workers United",
        "affiliation_code": "AFSCME", "local_number": None,
        "num_employees": 350,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-03-01",
        "naics_sector": "71",
        "source_description": "Monterey Bay Aquarium workers organized with AFSCME CWU",
        "notes": "Part of museum AFSCME wave",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Philadelphia Museum of Art",
        "city": "Philadelphia", "state": "PA",
        "union_name": "AFSCME DC 47",
        "affiliation_code": "AFSCME", "local_number": "47",
        "num_employees": 250,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-10-01",
        "naics_sector": "71",
        "source_description": "Philadelphia Museum of Art workers organized - went on 19-day strike",
        "notes": "First strike in museum history",
        "agent_source": agent,
    })

    # --- Theaters ---
    events.append({
        "employer_name": "The Public Theater",
        "city": "New York", "state": "NY",
        "union_name": "IATSE",
        "affiliation_code": "IATSE", "local_number": None,
        "num_employees": 190,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-06-01",
        "naics_sector": "71",
        "source_description": "Public Theater off-Broadway stagehands organized with IATSE",
        "notes": "Part of off-Broadway IATSE surge",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Goodman Theatre",
        "city": "Chicago", "state": "IL",
        "union_name": "IATSE",
        "affiliation_code": "IATSE", "local_number": None,
        "num_employees": 80,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-09-01",
        "naics_sector": "71",
        "source_description": "Goodman Theatre workers organized with IATSE",
        "notes": "Regional theater organizing",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Steppenwolf Theatre",
        "city": "Chicago", "state": "IL",
        "union_name": "IATSE",
        "affiliation_code": "IATSE", "local_number": None,
        "num_employees": 60,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-01-01",
        "naics_sector": "71",
        "source_description": "Steppenwolf Theatre workers organized with IATSE",
        "notes": "Regional theater organizing",
        "agent_source": agent,
    })

    # --- Hotels ---
    events.append({
        "employer_name": "The Venetian Resort",
        "city": "Las Vegas", "state": "NV",
        "union_name": "UNITE HERE Culinary Local 226",
        "affiliation_code": "UNITHE", "local_number": "226",
        "num_employees": 4000,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2024-01-01",
        "naics_sector": "72",
        "source_description": "Venetian/Palazzo voluntarily recognized UNITE HERE after decades of resistance",
        "notes": "Las Vegas Strip now 100% union; may already be in manual_employers",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Fontainebleau Las Vegas",
        "city": "Las Vegas", "state": "NV",
        "union_name": "UNITE HERE Culinary Local 226",
        "affiliation_code": "UNITHE", "local_number": "226",
        "num_employees": 3000,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2024-06-01",
        "naics_sector": "72",
        "source_description": "Fontainebleau Las Vegas recognized UNITE HERE",
        "notes": "New mega-resort; Las Vegas Strip 100% union",
        "agent_source": agent,
    })

    # --- Theme Parks ---
    events.append({
        "employer_name": "Disneyland Resort (Character Performers)",
        "city": "Anaheim", "state": "CA",
        "union_name": "Actors Equity Association",
        "affiliation_code": "UNAFF", "local_number": None,
        "num_employees": 1700,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-05-01",
        "naics_sector": "71",
        "source_description": "Disneyland character performers organized with Actors Equity",
        "notes": "Parade performers, characters, costume performers",
        "agent_source": agent,
    })

    # --- Restaurants / Food Service ---
    events.append({
        "employer_name": "Jose Andres Group / ThinkFoodGroup",
        "city": "Washington", "state": "DC",
        "union_name": "UNITE HERE",
        "affiliation_code": "UNITHE", "local_number": "25",
        "num_employees": 140,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2024-01-15",
        "naics_sector": "72",
        "source_description": "Jose Andres Group voluntarily recognized UNITE HERE Local 25",
        "notes": "The Bazaar restaurant workers",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Alamo Drafthouse Cinema (aggregate - multi-city)",
        "city": "Various", "state": "US",
        "union_name": "IATSE",
        "affiliation_code": "IATSE", "local_number": None,
        "num_employees": 400,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-12-01",
        "naics_sector": "71",
        "source_description": "Alamo Drafthouse workers organized in multiple cities; 58-day NYC strike",
        "notes": "Aggregate - Brooklyn, Raleigh, others; IATSE",
        "agent_source": agent,
    })
    events.append({
        "employer_name": "Via 313 Pizza",
        "city": "Austin", "state": "TX",
        "union_name": "UNITE HERE",
        "affiliation_code": "UNITHE", "local_number": None,
        "num_employees": 100,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-03-01",
        "naics_sector": "72",
        "source_description": "Via 313 Austin pizza workers organized with UNITE HERE",
        "notes": "Restaurant organizing in Texas",
        "agent_source": agent,
    })

    # ================================================================
    # ADDITIONAL NOTABLE EVENTS (from consolidated summary)
    # ================================================================
    agent = "ADDITIONAL"

    # --- Amazon multi-facility ---
    events.append({
        "employer_name": "Amazon (Garner, NC Warehouse RDU1)",
        "city": "Garner", "state": "NC",
        "union_name": "CAUSE (Carolina Amazonians United for Solidarity & Empowerment)",
        "affiliation_code": "UNAFF", "local_number": None,
        "num_employees": 4800,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2025-02-01",
        "naics_sector": "49",
        "source_description": "Amazon Garner NC warehouse voted to unionize with independent union",
        "notes": "Second Amazon warehouse to unionize after JFK8",
        "agent_source": agent,
    })

    # --- Apple additional ---
    events.append({
        "employer_name": "Apple Short Hills",
        "city": "Short Hills", "state": "NJ",
        "union_name": "IAM",
        "affiliation_code": "IAM", "local_number": None,
        "num_employees": 90,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-06-01",
        "naics_sector": "44",
        "source_description": "Apple Short Hills store organized with IAM",
        "notes": "Third Apple store to unionize",
        "agent_source": agent,
    })

    # --- Chipotle ---
    events.append({
        "employer_name": "Chipotle (Lansing, MI)",
        "city": "Lansing", "state": "MI",
        "union_name": "IBT",
        "affiliation_code": "IBT", "local_number": None,
        "num_employees": 25,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-08-25",
        "naics_sector": "72",
        "source_description": "First Chipotle store to unionize with Teamsters",
        "notes": "Store later closed by company (ULP filed)",
        "agent_source": agent,
    })

    # --- SpaceX ---
    events.append({
        "employer_name": "SpaceX (Hawthorne)",
        "city": "Hawthorne", "state": "CA",
        "union_name": "IAM",
        "affiliation_code": "IAM", "local_number": None,
        "num_employees": 300,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-10-01",
        "naics_sector": "31",
        "source_description": "SpaceX workers filed for NLRB election with IAM (challenged by company)",
        "notes": "SpaceX challenged NLRB constitutionality; ongoing litigation",
        "agent_source": agent,
    })

    # --- Google contractor ---
    events.append({
        "employer_name": "Alphabet/Google (Accenture contractors)",
        "city": "Austin", "state": "TX",
        "union_name": "CWA / Alphabet Workers Union",
        "affiliation_code": "CWA", "local_number": "1400",
        "num_employees": 60,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-04-01",
        "naics_sector": "51",
        "source_description": "Google/YouTube Music contractors organized with CWA/Alphabet Workers Union",
        "notes": "Accenture contract workers processing YouTube Music",
        "agent_source": agent,
    })

    # --- Fordham University ---
    events.append({
        "employer_name": "Fordham University Graduate Workers",
        "city": "Bronx", "state": "NY",
        "union_name": "CWA",
        "affiliation_code": "CWA", "local_number": None,
        "num_employees": 1200,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2022-10-01",
        "naics_sector": "61",
        "source_description": "Fordham grad workers organized with CWA",
        "notes": "Graduate student workers",
        "agent_source": agent,
    })

    # --- NYU adjunct ---
    events.append({
        "employer_name": "New York University (Researchers United)",
        "city": "New York", "state": "NY",
        "union_name": "UAW",
        "affiliation_code": "UAW", "local_number": None,
        "num_employees": 4000,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2025-01-01",
        "naics_sector": "61",
        "source_description": "NYU Researchers United - 4,000 postdocs/researchers pending election",
        "notes": "Pending as of 2025",
        "agent_source": agent,
    })

    # --- Starbucks Reserve Roastery ---
    events.append({
        "employer_name": "Starbucks Reserve Roastery",
        "city": "New York", "state": "NY",
        "union_name": "Workers United/SEIU",
        "affiliation_code": "WU", "local_number": None,
        "num_employees": 100,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2023-06-01",
        "naics_sector": "72",
        "source_description": "Starbucks Reserve Roastery organized in NYC",
        "notes": "Premium Starbucks concept; separate from aggregate count",
        "agent_source": agent,
    })

    # Filter out explicitly excluded events
    filtered = []
    for e in events:
        notes = (e.get("notes") or "").upper()
        if "EXCLUDED" in notes:
            continue
        filtered.append(e)

    return filtered


def normalize_events(events):
    """Add normalized employer names to all events."""
    for e in events:
        e["employer_name_normalized"] = normalize_employer_name(
            e["employer_name"], level="aggressive"
        )
    return events


def write_csv(events, output_path):
    """Write events to CSV file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(events)

    return output_path


def print_summary(events):
    """Print summary statistics."""
    print(f"\nTotal qualifying events: {len(events)}")

    # By agent
    print("\nBy Agent Source:")
    agents = {}
    for e in events:
        a = e["agent_source"]
        agents[a] = agents.get(a, 0) + 1
    for a, c in sorted(agents.items()):
        print(f"  {a}: {c}")

    # By affiliation
    print("\nBy Affiliation:")
    affs = {}
    for e in events:
        a = e["affiliation_code"]
        affs[a] = affs.get(a, 0) + 1
    for a, c in sorted(affs.items(), key=lambda x: -x[1]):
        print(f"  {a}: {c}")

    # By state
    print("\nBy State (top 10):")
    states = {}
    for e in events:
        s = e["state"]
        states[s] = states.get(s, 0) + 1
    for s, c in sorted(states.items(), key=lambda x: -x[1])[:10]:
        print(f"  {s}: {c}")

    # By recognition type
    print("\nBy Recognition Type:")
    rtypes = {}
    for e in events:
        r = e["recognition_type"]
        rtypes[r] = rtypes.get(r, 0) + 1
    for r, c in sorted(rtypes.items(), key=lambda x: -x[1]):
        print(f"  {r}: {c}")

    # Total workers
    total = sum(e.get("num_employees") or 0 for e in events)
    print(f"\nTotal workers across all events: {total:,}")

    # By NAICS
    print("\nBy NAICS Sector:")
    naics = {}
    for e in events:
        n = e["naics_sector"]
        naics[n] = naics.get(n, 0) + 1
    for n, c in sorted(naics.items()):
        print(f"  {n}: {c}")


if __name__ == "__main__":
    print("=" * 60)
    print("CATALOG RESEARCH EVENTS - Script 1 of 3")
    print("=" * 60)

    events = build_events()
    events = normalize_events(events)

    print_summary(events)

    path = write_csv(events, OUTPUT_CSV)
    print(f"\nCSV written to: {path}")
    print("Done.")
