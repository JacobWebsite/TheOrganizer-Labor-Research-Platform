-- ============================================================================
-- RESEARCH AGENT TABLES
-- Created: 2026-02-23
-- Purpose: Storage for the Deep Dive research agent (Phase 1)
--          Logging, fact storage, and vocabulary for consistent attribute naming
-- ============================================================================

-- ============================================================================
-- TABLE 1: research_fact_vocabulary
-- The "dictionary" of allowed attribute names. Every fact the agent stores
-- must use an attribute_name from this table. This keeps things consistent
-- so the learning system (Phase 2) can compare across runs.
-- ============================================================================
CREATE TABLE IF NOT EXISTS research_fact_vocabulary (
    id              SERIAL PRIMARY KEY,
    attribute_name  VARCHAR(100) UNIQUE NOT NULL,  -- e.g. 'employee_count', 'revenue'
    display_name    VARCHAR(200) NOT NULL,          -- e.g. 'Number of Employees', 'Annual Revenue'
    dossier_section VARCHAR(50) NOT NULL,           -- Which report section this belongs to
    data_type       VARCHAR(30) NOT NULL DEFAULT 'text',  -- text, number, currency, date, boolean, json
    existing_column VARCHAR(200),                   -- Maps to existing DB column (if any)
    existing_table  VARCHAR(200),                   -- Which existing table has this data
    description     TEXT,                           -- Human-readable explanation
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Allowed dossier sections (for reference):
--   'identity'    = Company Identity (name, industry, HQ, type)
--   'financial'   = Financial Profile (revenue, employees, growth)
--   'workforce'   = Workforce Intelligence (job types, demographics, postings)
--   'labor'       = Labor Relations History (unions, elections, ULPs)
--   'workplace'   = Workplace Issues (OSHA, wage theft, safety)
--   'assessment'  = Organizing Assessment (AI-generated analysis)
--   'sources'     = Sources & Confidence (meta-information about the research)

-- ============================================================================
-- SEED DATA: Fact Vocabulary
-- These are the allowed attribute names, organized by dossier section.
-- Maps to existing DB columns where possible.
-- ============================================================================

-- SECTION: identity (Company Identity)
INSERT INTO research_fact_vocabulary (attribute_name, display_name, dossier_section, data_type, existing_column, existing_table, description) VALUES
('legal_name',           'Legal Name',              'identity', 'text',    'employer_name',          'f7_employers_deduped',   'Official legal name of the company'),
('dba_names',            'DBA / Trade Names',       'identity', 'json',    'trade_name',             'whd_cases',              'Other names the company operates under'),
('parent_company',       'Parent Company',          'identity', 'text',    'parent_name',            'corporate_hierarchy',    'Name of the corporate parent, if any'),
('naics_code',           'NAICS Industry Code',     'identity', 'text',    'naics',                  'f7_employers_deduped',   '2-6 digit industry classification code'),
('naics_description',    'Industry Description',    'identity', 'text',    NULL,                     NULL,                     'Human-readable industry name'),
('hq_address',           'Headquarters Address',    'identity', 'json',    'city,state',             'f7_employers_deduped',   'Full headquarters address'),
('company_type',         'Company Type',            'identity', 'text',    NULL,                     NULL,                     'public, private, nonprofit, or government'),
('website_url',          'Company Website',         'identity', 'text',    'website_url',            'web_employer_profiles',  'Primary company website URL'),
('year_founded',         'Year Founded',            'identity', 'number',  'founding_year',          'web_employer_profiles',  'Year the company was established'),
('major_locations',      'Major Locations',         'identity', 'json',    NULL,                     NULL,                     'Key facility locations beyond HQ');

-- SECTION: financial (Financial Profile)
INSERT INTO research_fact_vocabulary (attribute_name, display_name, dossier_section, data_type, existing_column, existing_table, description) VALUES
('employee_count',       'Number of Employees',     'financial', 'number',   'latest_unit_size',      'f7_employers_deduped',   'Total employee count or best estimate'),
('revenue',              'Annual Revenue',          'financial', 'currency', 'sales_actual',          'mergent_employers',      'Annual revenue (exact or range)'),
('revenue_range',        'Revenue Range',           'financial', 'text',     'sales_range',           'mergent_employers',      'Revenue bracket if exact figure unavailable'),
('financial_trend',      'Financial Trend',         'financial', 'text',     NULL,                    NULL,                     'growing, stable, shrinking, or unknown'),
('exec_compensation',    'Executive Compensation',  'financial', 'json',     NULL,                    NULL,                     'Top executive pay (public companies only)'),
('federal_obligations',  'Federal Contract Value',  'financial', 'currency', 'total_obligations',     'federal_contract_recipients', 'Total federal contract dollar amount'),
('federal_contract_count','Federal Contract Count',  'financial', 'number',  'contract_count',        'federal_contract_recipients', 'Number of federal contracts'),
('nonprofit_revenue',    'Nonprofit Total Revenue', 'financial', 'currency', 'total_revenue',         'national_990_filers',    'Total revenue from IRS Form 990'),
('nonprofit_assets',     'Nonprofit Total Assets',  'financial', 'currency', 'total_assets',          'national_990_filers',    'Total assets from IRS Form 990');

-- SECTION: workforce (Workforce Intelligence)
INSERT INTO research_fact_vocabulary (attribute_name, display_name, dossier_section, data_type, existing_column, existing_table, description) VALUES
('workforce_composition','Workforce Composition',   'workforce', 'json',    NULL,                    'bls_industry_occupation_matrix', 'Estimated job types and percentages from BLS'),
('pay_ranges',           'Pay Ranges',              'workforce', 'json',    NULL,                    'bls_industry_occupation_matrix', 'Salary ranges for key positions'),
('job_posting_count',    'Active Job Postings',     'workforce', 'number',  NULL,                    NULL,                     'Number of current job listings found'),
('job_posting_details',  'Job Posting Details',     'workforce', 'json',    NULL,                    NULL,                     'Sample job titles, pay, locations from postings'),
('turnover_signals',     'Turnover Signals',        'workforce', 'text',    NULL,                    NULL,                     'Evidence of high/low turnover from postings or news'),
('demographic_profile',  'Worker Demographics',     'workforce', 'json',    NULL,                    NULL,                     'Typical demographics for this industry/area');

-- SECTION: labor (Labor Relations History)
INSERT INTO research_fact_vocabulary (attribute_name, display_name, dossier_section, data_type, existing_column, existing_table, description) VALUES
('existing_contracts',   'Existing Union Contracts', 'labor',   'json',    NULL,                    'f7_union_employer_relations', 'Current or recent union contracts'),
('union_names',          'Unions Representing',      'labor',   'json',    NULL,                    'f7_union_employer_relations', 'Names of unions with contracts'),
('nlrb_election_count',  'NLRB Elections',           'labor',   'number',  NULL,                    'nlrb_elections',         'Number of NLRB elections involving this employer'),
('nlrb_election_details','NLRB Election Details',    'labor',   'json',    NULL,                    'nlrb_elections',         'Dates, outcomes, vote counts for each election'),
('nlrb_ulp_count',       'ULP Charges',              'labor',   'number',  'nlrb_ulp_count',        'mv_unified_scorecard',   'Number of unfair labor practice charges'),
('nlrb_ulp_details',     'ULP Charge Details',       'labor',   'json',    NULL,                    'nlrb_cases',             'Types, filers, outcomes of ULP charges'),
('recent_organizing',    'Recent Organizing Activity','labor',  'text',    NULL,                    NULL,                     'Any recent organizing news or campaigns'),
('voluntary_recognition','Voluntary Recognitions',   'labor',   'json',    NULL,                    'nlrb_voluntary_recognition', 'Any voluntary union recognitions');

-- SECTION: workplace (Workplace Issues)
INSERT INTO research_fact_vocabulary (attribute_name, display_name, dossier_section, data_type, existing_column, existing_table, description) VALUES
('osha_violation_count',  'OSHA Violations',         'workplace', 'number',  NULL,                   'osha_violations_detail', 'Total OSHA violation count'),
('osha_violation_details','OSHA Violation Details',   'workplace', 'json',    NULL,                   'osha_violations_detail', 'Types, severity, penalties for violations'),
('osha_penalty_total',    'OSHA Penalties Total',     'workplace', 'currency',NULL,                   'osha_violations_detail', 'Total OSHA penalty dollars'),
('osha_serious_count',    'Serious OSHA Violations',  'workplace', 'number',  NULL,                   'osha_violations_detail', 'Count of serious/willful/repeat violations'),
('whd_case_count',        'Wage Theft Cases',         'workplace', 'number',  NULL,                   'whd_cases',              'Number of DOL Wage & Hour cases'),
('whd_backwages',         'Back Wages Owed',          'workplace', 'currency','backwages_amount',     'whd_cases',              'Total back wages assessed'),
('whd_penalties',         'WHD Penalties',             'workplace', 'currency','civil_penalties',      'whd_cases',              'Civil penalties from wage cases'),
('whd_employees_affected','Employees Affected by Wage Theft','workplace','number','employees_violated','whd_cases',             'Number of workers affected'),
('whd_repeat_violator',   'Repeat Wage Violator',     'workplace', 'boolean', 'flsa_repeat_violator', 'whd_cases',             'FLSA repeat violator flag'),
('safety_incidents',      'Safety Incidents',          'workplace', 'json',    NULL,                   'osha_accidents',        'Workplace accidents and incidents'),
('worker_complaints',     'Worker Complaints',         'workplace', 'text',    NULL,                   NULL,                    'Complaints or lawsuits from news/web'),
('recent_labor_news',     'Recent Labor News',         'workplace', 'json',    NULL,                   NULL,                    'News articles about labor issues');

-- SECTION: assessment (Organizing Assessment - AI-generated)
INSERT INTO research_fact_vocabulary (attribute_name, display_name, dossier_section, data_type, existing_column, existing_table, description) VALUES
('organizing_summary',    'Organizing Assessment',    'assessment', 'text',   NULL,                   NULL,                    'AI summary of organizing potential'),
('campaign_strengths',    'Campaign Strengths',       'assessment', 'json',   NULL,                   NULL,                    'Key advantages for an organizing campaign'),
('campaign_challenges',   'Campaign Challenges',      'assessment', 'json',   NULL,                   NULL,                    'Key obstacles to organizing'),
('similar_organized',     'Similar Employers Organized','assessment','json',  NULL,                   NULL,                    'Comparable employers that have been organized'),
('recommended_approach',  'Recommended Approach',      'assessment', 'text',  NULL,                   NULL,                    'Suggested organizing strategy');

-- SECTION: sources (Sources & Confidence - meta)
INSERT INTO research_fact_vocabulary (attribute_name, display_name, dossier_section, data_type, existing_column, existing_table, description) VALUES
('section_confidence',    'Section Confidence',       'sources',   'json',    NULL,                   NULL,                    'Confidence rating for each dossier section'),
('data_gaps',             'Data Gaps',                'sources',   'json',    NULL,                   NULL,                    'What was NOT found and where gaps remain'),
('source_list',           'Sources Consulted',        'sources',   'json',    NULL,                   NULL,                    'Every source checked with timestamps');


-- ============================================================================
-- TABLE 2: research_runs
-- One row per deep dive. The "cover page" of each research run.
-- ============================================================================
CREATE TABLE IF NOT EXISTS research_runs (
    id                  SERIAL PRIMARY KEY,
    employer_id         INTEGER,                    -- Links to f7_employers_deduped (if known)
    company_name        VARCHAR(500) NOT NULL,       -- The company being researched
    company_name_normalized VARCHAR(500),            -- Cleaned version for matching
    industry_naics      VARCHAR(6),                 -- NAICS code (for strategy lookup)
    company_type        VARCHAR(30),                -- public/private/nonprofit/government
    company_state       VARCHAR(2),                 -- State abbreviation
    employee_size_bucket VARCHAR(20),               -- small/medium/large (for strategy lookup)

    -- Run status & timing
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/running/completed/failed
    started_at          TIMESTAMP,
    completed_at        TIMESTAMP,
    duration_seconds    INTEGER,                    -- How long the whole run took

    -- Results summary
    total_tools_called  INTEGER DEFAULT 0,          -- How many tool calls were made
    total_facts_found   INTEGER DEFAULT 0,          -- How many facts were extracted
    sections_filled     INTEGER DEFAULT 0,          -- How many of 7 dossier sections got data
    dossier_json        JSONB,                      -- The complete finished report as JSON

    -- Cost tracking
    total_tokens_used   INTEGER DEFAULT 0,          -- Claude API tokens consumed
    total_cost_cents    INTEGER DEFAULT 0,          -- Estimated cost in cents

    -- Who triggered it
    triggered_by        VARCHAR(100),               -- User ID or 'system'

    -- Phase 2+ fields (filled in later)
    strategy_used       JSONB,                      -- Which strategy was recommended (Phase 2)
    overall_quality_score DECIMAL(4,2),             -- Auto-graded quality (Phase 3, 0-10)
    human_quality_score   DECIMAL(4,2),             -- Human override score (Phase 3)

    -- Progress tracking (for the frontend progress bar)
    current_step        VARCHAR(200),               -- e.g. "Searching OSHA violations..."
    progress_pct        INTEGER DEFAULT 0,          -- 0-100 percentage

    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_research_runs_employer ON research_runs(employer_id);
CREATE INDEX idx_research_runs_status ON research_runs(status);
CREATE INDEX idx_research_runs_naics ON research_runs(industry_naics);
CREATE INDEX idx_research_runs_created ON research_runs(created_at DESC);


-- ============================================================================
-- TABLE 3: research_actions
-- One row per tool call within a run. This is the detailed log.
-- Phase 2 analyzes this table to learn which tools work for which companies.
-- ============================================================================
CREATE TABLE IF NOT EXISTS research_actions (
    id                  SERIAL PRIMARY KEY,
    run_id              INTEGER NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
    tool_name           VARCHAR(100) NOT NULL,      -- e.g. 'search_osha', 'search_nlrb'
    tool_params         JSONB,                      -- What was searched (company name, NAICS, etc.)
    execution_order     INTEGER NOT NULL,            -- 1st call, 2nd call, etc.

    -- Results
    data_found          BOOLEAN DEFAULT FALSE,       -- Did the tool return useful data?
    data_quality        DECIMAL(3,2) DEFAULT 0.0,   -- Quality of what was found (0.0-1.0)
    facts_extracted     INTEGER DEFAULT 0,           -- How many facts came from this call
    result_summary      TEXT,                        -- Brief description of what was found

    -- Performance
    latency_ms          INTEGER,                    -- How long this tool call took
    cost_cents          INTEGER DEFAULT 0,          -- Cost for this specific call
    error_message       TEXT,                       -- Error details if something went wrong

    -- Context (what was known about the company at this point)
    company_context     JSONB,                      -- Company info available when this tool ran

    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_research_actions_run ON research_actions(run_id);
CREATE INDEX idx_research_actions_tool ON research_actions(tool_name);
CREATE INDEX idx_research_actions_found ON research_actions(data_found);


-- ============================================================================
-- TABLE 4: research_facts
-- One row per piece of information the agent found.
-- Every fact links to: the run, the tool that found it, and the vocabulary.
-- ============================================================================
CREATE TABLE IF NOT EXISTS research_facts (
    id                  SERIAL PRIMARY KEY,
    run_id              INTEGER NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
    action_id           INTEGER REFERENCES research_actions(id),  -- Which tool call found this
    employer_id         INTEGER,                    -- Links to f7_employers_deduped (if known)

    -- What was found
    dossier_section     VARCHAR(50) NOT NULL,       -- identity/financial/workforce/labor/workplace/assessment/sources
    attribute_name      VARCHAR(100) NOT NULL,       -- Must match research_fact_vocabulary
    attribute_value     TEXT,                        -- The actual data (stored as text, parsed by type)
    attribute_value_json JSONB,                     -- For complex data (lists, nested objects)

    -- Source tracking
    source_url          TEXT,                        -- URL or "database:table_name"
    source_type         VARCHAR(30) NOT NULL,        -- database, web_search, web_scrape, news, api
    source_name         VARCHAR(200),               -- Human-readable source name

    -- Quality
    confidence          DECIMAL(3,2) DEFAULT 0.5,   -- 0.0-1.0 confidence rating
    as_of_date          DATE,                       -- When this fact was true (e.g. '2024-12-31')
    contradicts_fact_id INTEGER REFERENCES research_facts(id),  -- If this conflicts with another fact

    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_research_facts_run ON research_facts(run_id);
CREATE INDEX idx_research_facts_employer ON research_facts(employer_id);
CREATE INDEX idx_research_facts_section ON research_facts(dossier_section);
CREATE INDEX idx_research_facts_attribute ON research_facts(attribute_name);

-- ============================================================================
-- PHASE 2 TABLE (created now but empty until Phase 2)
-- research_strategies: Aggregated success rates by industry/type/tool
-- ============================================================================
CREATE TABLE IF NOT EXISTS research_strategies (
    id                  SERIAL PRIMARY KEY,
    industry_naics_2digit VARCHAR(4),               -- e.g. '62' for healthcare, '31' for manufacturing
    company_type        VARCHAR(30),                -- public/private/nonprofit/government
    company_size_bucket VARCHAR(20),                -- small/medium/large
    tool_name           VARCHAR(100) NOT NULL,

    -- Performance stats
    times_tried         INTEGER DEFAULT 0,
    times_found_data    INTEGER DEFAULT 0,
    hit_rate            DECIMAL(5,4) DEFAULT 0.0,   -- times_found / times_tried
    avg_quality         DECIMAL(3,2) DEFAULT 0.0,   -- Average quality when data IS found
    avg_latency_ms      INTEGER DEFAULT 0,
    avg_cost_cents      INTEGER DEFAULT 0,
    recommended_order   INTEGER,                    -- Suggested position in research sequence

    last_updated        TIMESTAMP DEFAULT NOW(),

    -- Prevent duplicates: one row per industry/type/size/tool combination
    UNIQUE(industry_naics_2digit, company_type, company_size_bucket, tool_name)
);

CREATE INDEX idx_strategies_lookup ON research_strategies(industry_naics_2digit, company_type, company_size_bucket);

