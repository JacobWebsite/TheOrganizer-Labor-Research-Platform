// ---------------------------------------------------------------------------
// questionMap.js -- Maps research fact attribute_names to natural-language
// questions and provides helper utilities for the research feature.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// 1. QUESTION_MAP
//    Maps every known attribute_name to a plain-English research question.
// ---------------------------------------------------------------------------
export const QUESTION_MAP = {
  // -- identity --
  legal_name:              'What is the company\'s legal name?',
  dba_names:               'Does the company operate under any other names?',
  parent_company:          'Does this company have a parent company?',
  naics_code:              'What is the company\'s industry classification code?',
  naics_description:       'What industry does this company operate in?',
  hq_address:              'Where is the company headquartered?',
  company_type:            'Is this a public, private, or nonprofit company?',
  website_url:             'What is the company\'s website?',
  year_founded:            'When was this company founded?',
  major_locations:         'Where are the company\'s major facilities?',
  linkedin_url:            'What is the company\'s LinkedIn page?',
  company_officers:        'Who are the company\'s officers?',
  registered_agent:        'Who is the registered agent?',

  // -- corporate_structure --
  parent_type:             'What type of entity is the parent company?',
  subsidiaries:            'Does this company have known subsidiaries?',
  investors:               'Who are the major investors?',
  corporate_family:        'What does the corporate family look like?',
  ownership_chain:         'What is the ownership chain?',

  // -- locations --
  locations:               'What locations does the company operate from?',
  total_locations:         'How many locations does this company have?',
  headquarters:            'Where is the headquarters?',
  location_states:         'What states does this company have a presence in?',

  // -- leadership --
  ceo:                     'Who is the CEO or president?',
  executives:              'Who are the key executives?',
  local_leadership:        'Who are the local managers?',
  board_of_directors:      'Who sits on the board of directors?',

  // -- financial --
  employee_count:          'How many people does this company employ?',
  revenue:                 'What is the company\'s annual revenue?',
  revenue_range:           'What revenue bracket does this company fall into?',
  financial_trend:         'Is the company growing, stable, or shrinking?',
  exec_compensation:       'How much are the top executives paid?',
  federal_obligations:     'How much in federal contracts does this company hold?',
  federal_contract_count:  'How many federal contracts does the company have?',
  federal_contract_status: 'Is this a federal contractor?',
  nonprofit_revenue:       'What is the nonprofit\'s total revenue?',
  nonprofit_assets:        'What are the nonprofit\'s total assets?',
  local_subsidies:         'Has this company received taxpayer subsidies or grants?',

  // -- workforce --
  workforce_composition:   'What types of jobs make up the workforce?',
  pay_ranges:              'What are the pay ranges for key positions?',
  job_posting_count:       'How many job openings does the company currently have?',
  job_posting_details:     'What kinds of jobs is the company hiring for?',
  turnover_signals:        'Are there signs of high employee turnover?',
  demographic_profile:     'What do worker demographics look like?',
  competitor_wages:        'How do wages compare to competitors?',

  // -- labor --
  existing_contracts:      'Does this employer have any existing union contracts?',
  union_names:             'Which unions represent workers here?',
  nlrb_election_count:     'How many NLRB elections have involved this employer?',
  nlrb_election_details:   'What were the results of past NLRB elections?',
  nlrb_ulp_count:          'How many unfair labor practice charges have been filed?',
  nlrb_ulp_details:        'What were the ULP charges about?',
  recent_organizing:       'Has there been any recent organizing activity?',
  voluntary_recognition:   'Has this employer voluntarily recognized a union?',
  solidarity_network:      'Are there unionized sister facilities in the corporate family?',

  // -- workplace --
  osha_violation_count:    'How many OSHA violations does this employer have?',
  osha_violation_details:  'What were the OSHA violations for?',
  osha_penalty_total:      'How much has this employer paid in OSHA penalties?',
  osha_serious_count:      'How many serious OSHA violations were found?',
  whd_case_count:          'Has this employer been cited for wage theft?',
  whd_backwages:           'How much in back wages were owed?',
  whd_penalties:           'What were the WHD civil penalties?',
  whd_employees_affected:  'How many workers were affected by wage violations?',
  whd_repeat_violator:     'Is this a repeat wage violator?',
  safety_incidents:        'Have there been workplace safety incidents?',
  worker_complaints:       'What do workers say about working here?',
  recent_labor_news:       'What recent news has there been about labor issues?',
  warn_notices:            'Have there been any WARN Act layoff notices?',

  // -- assessment --
  organizing_summary:      'What is the overall organizing assessment?',
  campaign_strengths:      'What are the strengths for an organizing campaign?',
  campaign_challenges:     'What challenges would an organizing campaign face?',
  similar_organized:       'Have similar employers been organized?',
  recommended_approach:    'What organizing approach is recommended?',
  political_donations:     'What political donations has the company made?',
  data_summary:            'What is the data summary?',
  web_intelligence:        'What was found from web research?',
  source_contradictions:   'Were there any contradictions between sources?',

  // -- sources --
  section_confidence:      'How confident is the research in each section?',
  data_gaps:               'What data was not found?',
  source_list:             'What sources were consulted?',
}


// ---------------------------------------------------------------------------
// 2. questionFor(attributeName)
//    Returns the natural-language question for a given attribute. Falls back to
//    generating a readable question from the snake_case name.
// ---------------------------------------------------------------------------
export function questionFor(attributeName) {
  if (QUESTION_MAP[attributeName]) return QUESTION_MAP[attributeName]
  // Fallback: convert snake_case to "What is the [Readable Name]?"
  const readable = attributeName.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  return `What is the ${readable}?`
}


// ---------------------------------------------------------------------------
// 3. isNotFoundValue(value)
//    Detects placeholder / not-found values produced by the research agent
//    (agent.py line 647) and auto-grader (auto_grader.py line 63).
// ---------------------------------------------------------------------------
const NOT_FOUND_RE = /^(verified none|not searched|no data|not found|not available|n\/a|none|null|unknown|no results? found|no information (found|available)|no data found)/

export function isNotFoundValue(value) {
  if (value == null || value === '') return true
  if (typeof value !== 'string') return false
  const v = value.trim().toLowerCase()
  if (!v) return true
  return NOT_FOUND_RE.test(v)
}


// ---------------------------------------------------------------------------
// 4. KEY_LABELS + labelFor(key)
//    Human-readable short labels for attribute keys. Extracted from
//    DossierSection.jsx so both DossierSection and ResearchReview can share it.
// ---------------------------------------------------------------------------
export const KEY_LABELS = {
  legal_name: 'Legal Name',
  dba_names: 'DBA Names',
  naics_code: 'NAICS',
  naics_description: 'Industry',
  company_type: 'Type',
  union_names: 'Unions Present',
  nlrb_election_count: 'NLRB Elections',
  nlrb_ulp_count: 'ULP Charges',
  existing_contracts: 'Union Contracts',
  nlrb_election_details: 'Election Details',
  voluntary_recognition: 'Voluntary Recognitions',
  osha_violation_count: 'OSHA Violations',
  osha_serious_count: 'Serious Violations',
  osha_penalty_total: 'Total Penalties',
  osha_violation_details: 'Violation Details',
  whd_case_count: 'WHD Cases',
  workforce_composition: 'Workforce Composition',
  demographic_profile: 'Demographics',
  federal_contract_count: 'Federal Contracts',
  federal_obligations: 'Federal Obligations',
  organizing_summary: 'Summary',
  campaign_strengths: 'Strengths',
  campaign_challenges: 'Challenges',
  recommended_approach: 'Recommended Approach',
  similar_organized: 'Similar Organized Employers',
  source_list: 'Sources Used',
  data_gaps: 'Data Gaps',
  section_confidence: 'Confidence by Section',
  data_summary: 'Data Summary',
  web_intelligence: 'Web Intelligence',
  source_contradictions: 'Source Contradictions',
  registered_agent: 'Registered Agent',
  company_officers: 'Company Officers',
  competitor_wages: 'Competitor Wage Comparison',
  solidarity_network: 'Solidarity Network',
  local_subsidies: 'Taxpayer Subsidies',
  political_donations: 'Political Donations',
  warn_notices: 'WARN Act Notices',
  parent_company: 'Parent Company',
  parent_type: 'Parent Type',
  subsidiaries: 'Subsidiaries',
  investors: 'Investors',
  corporate_family: 'Corporate Family',
  ownership_chain: 'Ownership Chain',
  locations: 'Known Locations',
  total_locations: 'Total Locations',
  headquarters: 'Headquarters',
  location_states: 'States with Presence',
  ceo: 'CEO/President',
  executives: 'Executive Team',
  local_leadership: 'Local Management',
  board_of_directors: 'Board of Directors',
}

export function labelFor(key) {
  return KEY_LABELS[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
