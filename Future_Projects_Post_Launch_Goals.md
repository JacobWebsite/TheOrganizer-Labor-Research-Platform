**LABOR RELATIONS RESEARCH PLATFORM**

Future Projects & Post-Launch Goals

February 2026

*Aggregated from 15+ research and strategy documents*

+-----------------------------------------------------------------------+
| **What This Document Is**                                             |
|                                                                       |
| This document collects every major idea, research finding, and        |
| expansion plan that has been explored during the platform's           |
| development but isn't part of the launch roadmap. Think of it as a    |
| menu of "what comes next" --- organized by topic, with plain-language |
| explanations of what each project would do, why it matters for        |
| organizers, and roughly what it would take to build.                  |
|                                                                       |
| None of these projects block the launch. They're listed here so good  |
| ideas don't get lost and so you can prioritize based on what real     |
| users need most.                                                      |
+-----------------------------------------------------------------------+

At a Glance: All Future Projects

Each project falls into one of three priority tiers based on how
directly it helps organizers and how much existing groundwork already
supports it.

  ------------------------ -------------- ------------ ---------------- --------------
  **Project**              **Priority**   **Effort**   **Key Payoff**   **Depends On**

  **Union Contract         **HIGH**       9--12 months Searchable       Scraping
  Database (CBA)**                                     contract         pipeline
                                                       language         

  **Web Scraper: Union     **HIGH**       4--6 weeks   Public-sector    Crawl4AI setup
  Sites**                                              employers        

  **Web Scraper: Employer  **HIGH**       4--6 weeks   Company profiles Crawl4AI setup
  Sites**                                              at scale         

  **SEC EDGAR              **HIGH**       3--4 weeks   Corporate        Matching
  Integration**                                        hierarchy + EIN  pipeline
                                                       match            

  **Prevailing Wage        **HIGH**       6--8 weeks   Subsidy-based    Geographic
  Intelligence**                                       organizing       analysis
                                                       targets          

  **Advanced Scoring       **MEDIUM**     4--6 weeks   \"Should be      Better match
  (Propensity)**                                       union\"          rates
                                                       probability      

  **Gower Similarity       **MEDIUM**     2--3 weeks   \"87% similar to NAICS coverage
  Engine**                                             unionized X\"    

  **State PERB Data**      **MEDIUM**     6--8 weeks   First-ever       FOIA/FOIL
                                                       public sector    requests
                                                       dataset          

  **Entity Resolution      **MEDIUM**     2--3 weeks   Higher match     Current
  Upgrade (Splink)**                                   rates everywhere matching done

  **\"Union-Lost\"         **MEDIUM**     2--4 weeks   What happens     Historical
  Historical Analysis**                                after unions     data loaded
                                                       leave            

  **Occupation-Based       **MEDIUM**     2--3 weeks   Cross-industry   BLS OEWS data
  Similarity**                                         comparisons      

  **Contract Expiration    **MEDIUM**     1--2 weeks   Timely           User accounts,
  Alerts**                                             organizing       email
                                                       triggers         

  **CPS Microdata          **FUTURE**     2--3 weeks   Custom density   IPUMS access
  (Granular Density)**                                 cross-tabs       

  **Text-Based Employer    **FUTURE**     3--4 weeks   AI-powered       Company
  Embeddings**                                         employer         descriptions
                                                       matching         

  **Multi-Tenant Union     **FUTURE**     2--3 weeks   Each union sees  User auth
  Workspaces**                                         their territory  system

  **Campaign Tracking**    **FUTURE**     2--3 weeks   Track organizing User accounts
                                                       stages           

  **News & Media           **FUTURE**     2--3 weeks   Auto-detect      News API
  Monitoring**                                         labor news       subscription

  **Board Report           **FUTURE**     1--2 weeks   One-click PDF    Frontend +
  Generation**                                         for meetings     export

  **5-Area Frontend        **FUTURE**     3--4 weeks   Full navigation  Phase 2
  Expansion**                                          structure        architecture
  ------------------------ -------------- ------------ ---------------- --------------

1\. Union Contract Database (CBA Analysis at Scale)

What it is

A system that collects thousands of actual union contracts (called
Collective Bargaining Agreements, or CBAs), reads them using AI, pulls
out the important parts --- wages, grievance procedures, seniority
rules, health benefits --- and makes them searchable. An organizer could
type "show me grievance procedures in healthcare contracts in New York"
and get back actual contract language from dozens of agreements.

Why it matters

Right now, if an organizer wants to know "what did other unions
negotiate for health benefits in similar workplaces?" they have to
manually hunt through PDF contracts one by one. This would let them
search across thousands of contracts instantly. It also answers a
question that comes up in every organizing conversation: "What would a
union contract actually look like for us?"

Where the contracts come from

There are over 25,000 contracts freely available from public sources.
The biggest are SeeThroughNY (about 17,000 New York public-sector
contracts), New Jersey PERC (6,366 contracts), Ohio SERB (3,000--5,000),
the federal OPM database (1,000--2,000), and the DOL/OLMS collection
(1,500--2,500). The Cornell Kheel Center holds a massive historical
archive going back to 1887. None of these offer a one-click bulk
download --- they all require some amount of automated scraping or
public records requests to get the files.

How the AI reading works

The system would work in layers. First, it figures out whether each
contract PDF is digital text or a scanned image. Digital PDFs get read
instantly by a free tool called PyMuPDF. Scanned PDFs get sent to a
cloud service (like Mistral OCR) that reads the images --- this costs
about \$1 per 1,000 pages. Then an AI language model reads through the
text and identifies specific types of clauses: wages, benefits,
grievance procedures, management rights, and so on. Research shows these
AI models can correctly identify about 86% of contract clauses without
any special training.

What it would cost

The total cost to process 5,000 contracts would be roughly
\$250--\$1,200 for OCR and AI extraction, plus about \$100--350/month in
server costs. The entire first year would run about \$1,500--5,000. The
most expensive part is the AI clause extraction, but using batch
processing (sending contracts in bulk overnight at discounted rates)
keeps this manageable.

The academic foundation

A major research paper by Arold, Ash, MacLeod, and Naidu (NBER, March
2025) analyzed 32,402 Canadian union contracts and developed a method
for understanding the legal meaning of contract language by looking at
specific words like "shall," "may," and "shall not." These words signal
different levels of legal force --- "employees may request overtime" is
very different from "employees shall receive overtime" even though the
sentences look similar. Their code is publicly available and could be
adapted for this platform.

Timeline

9--12 months for a solo developer to reach 5,000 processed contracts
with searchable clause extraction. Months 1--2 for the ingestion
pipeline, months 3--4 for search and basic extraction, months 5--8 for
scaling and quality, months 9--12 for analytics and cross-contract
comparisons.

2\. Web Scraping Pipeline (Union + Employer Websites)

What it is

Two focused tools that automatically visit websites and extract useful
information. One visits union websites to find data about locals,
officers, and employers they represent. The other visits company
websites to fill in gaps in employer records --- things like company
descriptions, employee counts, and industry details.

Why it matters

Government databases miss a lot. Public-sector unions often don't file
with the federal Department of Labor at all, which means thousands of
employers and union locals are invisible in the current data. Union
websites often list this information publicly but nobody has ever
systematically collected it. On the employer side, the platform knows an
employer's name and address from government filings but often has no
description of what the company actually does, how many people work
there, or who runs it.

The union scraper: what was discovered

After investigating all 12 major unions, a clear picture emerged.
Teamsters has the richest publicly available directory --- every local
listed on a single page with officers, phone numbers, emails, and
industry affiliations across 22 divisions. AFSCME is the most
strategically valuable because local union names often include the
employer name (e.g., "Local 1072 \| University of Maryland"), providing
a direct path to identifying thousands of public-sector employers that
don't appear in any federal database. UNITE HERE publishes detailed
officer information for every local. CWA uses a filterable directory by
district and sector.

On the harder end, AFT requires a member login, IBEW's directory runs
entirely in JavaScript (meaning a simple web request gets nothing back
--- you need a full simulated browser), and UAW's directory has the same
problem. SEIU's finder shows local names and states but no contact
details at the national level.

Why union sites are easier to scrape than company sites

Most union websites run on WordPress, which is a widely-used website
platform that has a built-in system for sharing data in a structured
format (called a REST API). This means that instead of trying to read
the messy visual layout of a webpage, the scraper can often just ask the
website for its data directly and get back clean, organized information.
Union sites also rarely invest in anti-bot protection, have low traffic
(so rate limiting is generous), and most of their public content loads
as plain HTML rather than requiring a browser to render JavaScript.

The employer enrichment tool

For companies, tools like Firecrawl can visit a company website,
understand its layout using AI, and extract structured information like
industry, services offered, employee count, headquarters location, and
founding year. On its own benchmark, Firecrawl achieves about 87--94%
accuracy. The main risk is that the AI sometimes makes up
plausible-sounding information when the real data isn't on the page
(called "hallucination"), so every extraction needs a confidence score
and human spot-checking.

What's already been proven

The AFSCME scraper prototype already crawled 295 profiles, processed 103
sites, and extracted 160 employers. This validates the approach and
shows it works at a meaningful scale. The next step would be expanding
to Teamsters (338 locals), SEIU, UFCW, and UNITE HERE.

3\. SEC EDGAR Corporate Intelligence

What it is

The SEC (Securities and Exchange Commission) requires publicly traded
companies to file detailed reports about their business. These filings
contain a goldmine of labor-relevant data: employee counts, how much
companies spend on labor, whether they mention unions or collective
bargaining in their risk factors, executive compensation, and ---
critically --- lists of subsidiary companies they own.

Why it matters

Right now, when the platform shows an employer like "ABC Healthcare
Corp," it might not know that ABC is actually owned by a giant national
chain with 50,000 employees and a history of fighting unions. SEC
filings connect the dots between parent companies and their
subsidiaries, revealing corporate structures that matter enormously for
organizing strategy. They also provide employee counts for thousands of
companies in a structured, machine-readable format.

The EIN connection (this is the big deal)

Every SEC filing includes the company's EIN (Employer Identification
Number) --- the same ID that appears in DOL filings and IRS records.
This means the platform could directly link SEC corporate data to
existing employer records without any fuzzy name-matching guesswork. A
bulk download of all SEC company records (about 800,000 entities)
provides a master lookup table of CIK-to-EIN mappings that enables
automatic connections across databases.

What's in the filings

-   **10-K Annual Reports:** The richest source. Since November 2020,
    companies must disclose their "human capital" practices --- about
    58% include workforce demographics, turnover rates, and labor
    relations details. The Risk Factors section often mentions union
    activity, CBA expirations, and strike risk.

-   **8-K Current Reports:** Real-time filings about major events,
    including layoffs and plant closures. These could serve as early
    warning signals.

-   **Exhibit 21 (Subsidiary Lists):** Companies list every subsidiary
    they own. Parsing these reveals which employers in the platform's
    database are actually connected through parent companies.

-   **XBRL Tags:** Structured, machine-readable data fields. One
    particularly valuable tag literally stores CBA expiration dates for
    companies participating in multiemployer pension plans. The platform
    could automatically flag when contracts are about to expire.

Existing tools

The Python library "edgartools" (1,400+ stars on GitHub, very actively
maintained) handles all of this --- parsing filings, extracting
financial data, reading XBRL tags. It even has a built-in AI
integration. A companion tool called "sec-edgar-downloader" handles bulk
file downloads with proper rate limiting so the SEC doesn't block
access.

4\. Prevailing Wage & Subsidy Intelligence

What it is

Across the country, government programs give tax breaks, grants, and
subsidies to private employers --- but with strings attached. Many
require paying "prevailing wages" (essentially union-scale pay rates) or
hiring through registered apprenticeship programs. These programs create
public records showing exactly which employers are receiving public
money, what wage obligations they're under, and whether they're
complying. This project would build a database cross-referencing subsidy
recipients with the platform's existing employer data.

Why it matters for organizing

The gap between what employers are required to pay and what they
actually pay is itself an organizing opportunity. An organizer who can
show that a specific developer is receiving millions in tax breaks but
using non-union contractors on a project that legally requires
prevailing wages has both a compliance complaint and a powerful
organizing story. The Inflation Reduction Act alone has created
prevailing wage obligations on an estimated 3.9 million construction
jobs at over 6,000 clean energy projects nationwide.

Major programs identified

Research identified over 25 specific programs at every level of
government:

-   **Federal:** The Inflation Reduction Act (5x tax credit multiplier
    for prevailing wage compliance), CHIPS Act (\$52.7 billion in
    semiconductor subsidies with Davis-Bacon requirements), and the
    Infrastructure Investment and Jobs Act.

-   **New York:** The 485-x tax abatement (\$1.7 billion/year in
    foregone revenue, covering 56% of all new multifamily construction
    in NYC), co-op/condo prevailing wage requirements, and IDA project
    requirements statewide.

-   **New Jersey:** The most comprehensive state coverage --- prevailing
    wage attached to virtually every economic development authority
    program across multiple agencies.

-   **California:** The most expansive definition of "public funds" in
    the country. A subsidy must be both under \$500,000 and under 2% of
    project costs to avoid triggering prevailing wage.

-   **Other states:** Connecticut (\$1M threshold), Minnesota (first to
    mandate prevailing wage on affordable housing tax credits),
    Washington (tiered system linking tax deferral size to labor
    standards).

Ten concrete organizing applications

The research document includes ten specific, actionable strategies,
including: cross-referencing NYC 485-x recipients to identify non-union
contractors, using film tax credit data to track non-union productions
receiving state subsidies, leveraging the IRA's 80% credit penalty as
organizing leverage against clean energy developers, mining Chicago's
TIF portal to find subsidized employers bypassing labor standards,
filing False Claims Act whistleblower complaints as organizing leverage
(LIUNA already won a \$255,000 settlement doing this in New York), and
targeting CHIPS Act recipients like TSMC for construction trades
organizing.

Key databases

Good Jobs First's Subsidy Tracker (722,000+ entries nationally), NYC
Department of Finance property tax benefit lookup, the DOL's interactive
IRA project map, Chicago's TIF Portal, and SAM.gov for federal
prevailing wage rates by location and trade.

5\. Advanced Scoring: Propensity Model & Gower Distance

What's wrong with the current scoring

The current scorecard looks at each employer in isolation and checks a
list of factors: How big is the workplace? How unionized is the
industry? Any OSHA violations? Any government contracts? Each factor
gets some points, you add them up, and that's the score. This works, but
it misses the most powerful question an organizer actually asks: "Which
non-union employers look the most like employers that already have a
union?"

Gower Distance: \"How similar are these two employers?\"

Gower Distance is a math formula that compares two employers across
everything the platform knows about them --- industry, size, location,
violation history, government contracts --- and produces a single number
between 0 (completely different) and 1 (basically twins). The practical
advantage is that it handles missing data gracefully. If you don't know
an employer's revenue but you know everything else, it just skips that
factor and compares on what it has. With government data, you're always
missing something, so this matters a lot.

Instead of "this employer scored 35 out of 62," an organizer would see:
"This non-union nursing home in Queens with 200 employees and 3 OSHA
violations is 87% similar to this unionized nursing home in Brooklyn
with 180 employees and 4 OSHA violations that SEIU already represents."
That's a much more compelling pitch.

Propensity Score: \"What's the probability this should be union?\"

This is the most powerful idea. The platform has thousands of employers
where it knows whether they're unionized. It also knows things about
those employers --- their industry, size, location, violation history. A
statistical model can learn the pattern: "Employers that look like THIS
tend to be unionized." Then you apply that pattern to non-union
employers. The model says: "Based on everything I know about this
employer, there's a 78% chance it should be unionized --- meaning it
looks almost identical to employers that already are." That 78% becomes
the organizing score.

The key advantage over the hand-picked scoring: the data picks the
weights instead of a human guessing. Maybe OSHA violations matter way
more than employer size. Maybe government contracts matter less than
expected. The model figures this out from actual patterns in the 60,000+
employer database. The catch is that it needs good examples of both
unionized and non-unionized employers, which is where the Mergent data
and OSHA establishment records come in.

Entity Resolution Upgrade (Splink)

Neither scoring improvement matters much if the platform can't reliably
tell that "WALMART INC" in OSHA data, "Wal-Mart Stores, Inc." in NLRB
records, and "WAL MART STORES INC" in wage theft data are all the same
company. The current matching system already handles this through a
5-tier pipeline and achieves strong results (96.2% on F-7 to OLMS
matching). But a tool called Splink --- built by the UK Ministry of
Justice, used by Australia's national statistics agency --- takes a
probabilistic approach. Instead of "match or no match," it says "92%
chance these are the same entity." It has native PostgreSQL support and
can link a million records in about a minute on a regular laptop.

6\. State PERB Data (Original Contribution)

What it is

PERB stands for Public Employment Relations Board. Most states have one
(sometimes called something slightly different), and they oversee labor
relations for state and local government workers --- teachers, police,
firefighters, sanitation workers, municipal employees. These agencies
maintain records of representation cases, union certifications, and
sometimes contract filings. But no one has ever built a tool that
collects this data from across multiple states into one searchable
database.

Why it matters

Federal labor data has a big blind spot: public-sector workers. The
Department of Labor's OLMS system primarily tracks private-sector and
federal employee unions. State and local government workers --- who make
up a huge share of union membership in the United States --- fall under
state jurisdiction. Without PERB data, the platform is essentially
invisible to thousands of public-sector employers and the unions that
represent their workers.

The opportunity

No open-source tool exists for scraping state PERB data. Building
scrapers for NY PERB, CA PERB, and IL ILRB would be a first-of-its-kind
resource. Each state has a different format and access method, and some
will require public records requests (FOIL in New York, Public Records
Act in California). The work is labor-intensive but the result would be
one of the platform's biggest differentiators --- data that literally no
one else has compiled.

7\. \"Union-Lost\" Historical Analysis

What it is

The platform already contains 52,760 historical employer records ---
workplaces that once had union contracts but no longer do. Matching
these against OSHA violations, wage theft records, and NLRB activity
could answer questions like: "Which employers decertified their union?
What happened to working conditions after the union left? Did OSHA
violations go up? Did wage theft increase?"

Why it matters

This is research-grade analysis that serves two purposes. For
organizers, it provides ammunition: "Look what happened at Company X
after workers lost their union --- safety violations tripled." For
academic partners and advocacy, it contributes to the broader evidence
base about the effects of unionization on workplace conditions. This
kind of before-and-after analysis using linked administrative data is
exactly what labor economists study, and the platform is uniquely
positioned to do it because it has both the historical records and the
cross-database matching infrastructure.

8\. Occupation-Based Similarity

What it is

Instead of comparing employers only by their industry code (NAICS),
compare them by the types of workers they actually employ. The Bureau of
Labor Statistics publishes data showing what occupations exist in each
industry. Two employers with different industry codes but similar worker
mixes --- lots of warehouse workers, lots of truck drivers --- are
highly comparable for organizing purposes even if one is classified as
"retail" and the other as "transportation."

How it works (simply)

Think of each employer as having a "fingerprint" based on the types of
workers it employs. A hospital's fingerprint might be 30% nurses, 15%
aides, 10% administrative, 5% maintenance, and so on. A nursing home has
a different mix but a lot of overlap. The math compares these
fingerprints and produces a similarity score. This captures something
that industry codes completely miss: a call center and a hospital
billing office employ very similar workforces even though their NAICS
codes are totally different.

What it takes

The BLS OEWS (Occupational Employment and Wage Statistics) program
publishes this cross-tabulation data freely. The math involved is called
"cosine similarity" on occupation vectors --- a standard technique that
Python handles in a few lines of code. The main work is loading the BLS
staffing pattern data and linking it to the employer records through
their NAICS codes.

9\. Additional Future Projects

Contract Expiration Alerts

Automatic email notifications when contracts in a user's territory are
expiring in the next 3, 6, or 12 months. Contract expiration is one of
the most important triggers for organizing activity --- it's when
workers are most engaged with labor issues and when rival unions might
make moves. This requires the FMCS data (already integrated), user
accounts, and a basic email service like SendGrid (free tier available).

CPS Microdata for Granular Density

Right now, BLS only publishes union density at about 50 broad industry
categories. The raw survey data (called CPS microdata, available through
IPUMS) allows custom cross-tabulations at any level --- union density
for healthcare workers in Ohio, or for manufacturing workers in the
Chicago metro area. This is the difference between knowing "11% of
healthcare workers nationally are in unions" and knowing "23% of
healthcare workers in your specific region are in unions."

Text-Based Employer Embeddings

An AI technique where company descriptions (from websites, job postings,
or LinkedIn profiles) get converted into mathematical "fingerprints."
Companies with similar descriptions end up with similar fingerprints.
Research shows this outperforms traditional industry codes for
identifying comparable businesses. A hospital and an ambulatory care
center might have different NAICS codes but their descriptions would
reveal they're functionally very similar workplaces. This requires
company description data from web scraping.

Multi-Tenant Union Workspaces

Each union organization gets their own view of the platform showing only
their territory, their employers, and their targets. Union A can't see
Union B's internal notes or priority rankings. This transforms the
platform from a research tool into a collaborative workspace for
organizing teams.

Campaign Tracking

Let organizers mark employers as "active campaign" and track stages from
research to outreach to petition to election to contract. Over time,
this builds a proprietary dataset of organizing outcomes that feeds back
into the scoring model --- the platform learns from real-world results
which types of targets lead to successful campaigns.

News & Media Monitoring

Automatically scan news for labor-related stories --- strikes,
organizing drives, employer controversies --- and link them to employers
in the database. This could use a news API (\$449/month for full access)
or free Google News RSS feeds (slower, less reliable). AI would extract
employer names from articles and match them to database records.

Board Report Generation

One-click PDF or spreadsheet exports designed for union board
presentations: territory overview, top targets with supporting evidence,
trend charts, and data freshness statements. This is a "last mile"
feature that makes the platform useful for the actual meetings where
organizing decisions get made.

5-Area Frontend Expansion

When the platform is mature enough, expand from the initial 4-screen
structure to a 5-area layout: Dashboard (quick snapshot), My Territory
(union-specific coverage map), Employer Research (detail and corporate
family), Organizing Targets (scorecard, comparables, and evidence), and
Data Explorer (density, trends, elections, analytics). The initial
frontend architecture was designed to allow this expansion without
rebuilding navigation.

10\. Open Source Tools That Power These Projects

One of the most important findings from research is that most of the
technical building blocks for these projects already exist as free,
open-source software. Here are the most important ones:

  ------------------ ----------------- ----------------------------------------
  **Tool**           **What It Does**  **Why It Matters for This Platform**

  **labordata        27 repos covering Already aggregates 40.5 million rows of
  (GitHub org)**     NLRB, OSHA, WHD,  labor data into a unified warehouse.
                     OLMS, FMCS        Many repos build PostgreSQL databases
                                       directly.

  **edgartools**     SEC EDGAR parsing Extracts employee counts, financial
                     (1,400 stars)     data, XBRL tags, and subsidiary lists.
                                       Has a built-in AI integration. 24
                                       releases in 60 days.

  **Splink**         Probabilistic     Links a million records in \~1 minute on
                     record matching   a laptop. Native PostgreSQL support.
                     (1,800 stars)     Built by UK Ministry of Justice, used by
                                       Australia's stats agency.

  **Crawl4AI**       Web scraping for  Already in use on the platform. Handles
                     AI pipelines      JavaScript-rendered pages and converts
                                       web content to AI-friendly formats.

  **LangExtract**    AI-powered        Purpose-built for pulling structured
                     structured        data from long documents (like
                     extraction        contracts). Links every extraction back
                                       to its source location.

  **Firecrawl**      Website-to-JSON   Visits a company website and returns
                     extraction (81K   structured data matching a schema you
                     stars)            define. 87--94% accuracy on company
                                       profiles.

  **Docling (IBM)**  Document parsing, Handles PDFs, DOCX, HTML through one
                     97.9% table       interface. Critical for extracting wage
                     accuracy          tables from contracts.

  **IRSx /           IRS Form 990      Converts nonprofit tax filings into
  990-xml-reader**   parser            database records. Extracts employee
                                       counts, executive compensation, and
                                       organization details.

  **RapidFuzz**      Fast string       Compares employer names 10--100x faster
                     matching (3,700   than alternatives. Essential for
                     stars)            matching "WALMART INC" to "Wal-Mart
                                       Stores, Inc."

  **pgvector**       Vector search in  Enables semantic search ("find contracts
                     PostgreSQL        with similar language") without adding a
                                       separate search server.
  ------------------ ----------------- ----------------------------------------

The only significant gap in the open-source ecosystem: no projects exist
for state PERB data. Building scrapers for NY PERB, CA PERB, and IL ILRB
would be an original contribution.

11\. Suggested Sequencing

Not all of these projects are equal. Some unlock other projects, some
provide immediate value, and some are aspirational long-term goals.
Here's a suggested order based on how much each project helps organizers
and what it enables next:

Wave 1: Foundation (First 1--3 months post-launch)

These either have existing groundwork or provide immediate value:

-   **Web Scraper (Union Sites) ---** AFSCME prototype already works.
    Expanding it fills the public-sector data gap that's the platform's
    biggest blind spot.

-   **SEC EDGAR Integration ---** The EIN matching makes this
    low-friction. Reveals corporate hierarchies behind seemingly
    independent employers.

-   **Contract Expiration Alerts ---** Small feature, big impact. Uses
    data already in the system.

Wave 2: Intelligence (Months 3--6)

These deepen analytical power:

-   **Gower Similarity Engine ---** One Python library, existing data.
    Transforms how organizers see employer relationships.

-   **Web Scraper (Employer Sites) ---** Fills the "what does this
    company actually do" gap.

-   **Entity Resolution Upgrade (Splink) ---** Pushes match rates
    higher, which makes everything else more accurate.

-   **State PERB Data ---** Start with FOIA/FOIL requests early (they
    take time). Build scrapers as data arrives.

Wave 3: Advanced (Months 6--12)

These require more data and infrastructure:

-   **Propensity Scoring Model ---** Needs better match rates and
    non-union employer reference data from Waves 1--2.

-   **Union Contract Database ---** Major project. Start ingestion in
    Wave 2, scale extraction in Wave 3.

-   **Prevailing Wage Intelligence ---** Cross-referencing subsidy
    databases with the platform's employer records.

-   **Union-Lost Analysis ---** Historical employer records + improved
    matching = before-and-after research.

-   **Occupation-Based Similarity ---** BLS data loading +
    straightforward math.

Wave 4: Platform Maturity (Year 2+)

These depend on having real users and feedback:

-   **Multi-Tenant Union Workspaces ---** Needs user accounts and real
    organizational partners.

-   **Campaign Tracking ---** Only valuable once organizers are actively
    using the platform.

-   **News & Media Monitoring ---** Nice-to-have that benefits from a
    mature employer database.

-   **Text-Based Employer Embeddings ---** Requires company description
    data from web scraping.

-   **CPS Microdata ---** Enhances density calculations but current BLS
    data works for now.

-   **Board Report Generation ---** Needs the frontend and data to be
    stable before exports matter.

-   **5-Area Frontend Expansion ---** Architectural groundwork is done;
    expand when usage patterns are clear.

12\. Key Principle: Build What Organizers Need, Not What's Technically
Interesting

Every project in this document is technically feasible and
intellectually interesting. But the platform succeeds only if it becomes
something organizers reach for when making real decisions about where to
invest their limited time and resources. The most important filter for
deciding what to build next is simple: talk to people who would actually
use it, and build the thing they ask for.

The projects marked HIGH priority are the ones most likely to produce
that "must-have" reaction --- they fill visible gaps in the current data
(public-sector employers, corporate hierarchies, subsidy connections) or
transform how organizers evaluate targets (similarity comparisons
instead of abstract scores). The FUTURE projects are genuinely valuable
but depend on the platform first proving its worth with the basics.

This document should be revisited after every major milestone and
updated based on what users actually want.

*--- End of Document ---*
