import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { FactRow } from './FactRow'
import {
  Building2, Users, HardHat, DollarSign, Briefcase, ClipboardCheck, Database,
} from 'lucide-react'

const SECTION_META = {
  identity:   { icon: Building2,      label: 'Company Identity',    defaultOpen: true },
  labor:      { icon: Users,          label: 'Labor Relations',     defaultOpen: true },
  workforce:  { icon: Briefcase,      label: 'Workforce',           defaultOpen: false },
  workplace:  { icon: HardHat,        label: 'Workplace Safety',    defaultOpen: false },
  financial:  { icon: DollarSign,     label: 'Financial',           defaultOpen: false },
  assessment: { icon: ClipboardCheck, label: 'Overall Assessment',  defaultOpen: true },
  sources:    { icon: Database,       label: 'Data Sources',        defaultOpen: false },
}

// Labels for known keys so they render nicely
const KEY_LABELS = {
  legal_name: 'Legal Name', dba_names: 'DBA Names', naics_code: 'NAICS', naics_description: 'Industry',
  company_type: 'Type', union_names: 'Unions Present', nlrb_election_count: 'NLRB Elections',
  nlrb_ulp_count: 'ULP Charges', existing_contracts: 'Union Contracts',
  nlrb_election_details: 'Election Details', voluntary_recognition: 'Voluntary Recognitions',
  osha_violation_count: 'OSHA Violations', osha_serious_count: 'Serious Violations',
  osha_penalty_total: 'Total Penalties', osha_violation_details: 'Violation Details',
  whd_case_count: 'WHD Cases', workforce_composition: 'Workforce Composition',
  demographic_profile: 'Demographics', federal_contract_count: 'Federal Contracts',
  federal_obligations: 'Federal Obligations', organizing_summary: 'Summary',
  campaign_strengths: 'Strengths', campaign_challenges: 'Challenges',
  recommended_approach: 'Recommended Approach', similar_organized: 'Similar Organized Employers',
  source_list: 'Sources Used', data_gaps: 'Data Gaps', section_confidence: 'Confidence by Section',
  data_summary: 'Data Summary', web_intelligence: 'Web Intelligence',
  source_contradictions: 'Source Contradictions',
  registered_agent: 'Registered Agent', company_officers: 'Company Officers',
  competitor_wages: 'Competitor Wage Comparison', solidarity_network: 'Solidarity Network',
  local_subsidies: 'Taxpayer Subsidies', political_donations: 'Political Donations',
  warn_notices: 'WARN Act Notices',
}

function labelFor(key) {
  return KEY_LABELS[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Render a single value — handles strings, numbers, arrays, objects. */
function RenderValue({ value }) {
  if (value == null) return <span className="text-muted-foreground">-</span>

  // String — may be long narrative text
  if (typeof value === 'string') {
    if (value.length > 200) {
      return <p className="text-sm whitespace-pre-wrap">{value}</p>
    }
    return <span>{value}</span>
  }

  // Number
  if (typeof value === 'number') {
    return <span>{value.toLocaleString()}</span>
  }

  // Boolean
  if (typeof value === 'boolean') {
    return <span>{value ? 'Yes' : 'No'}</span>
  }

  // Array of strings
  if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'string') {
    return (
      <ul className="list-disc list-inside space-y-0.5">
        {value.map((item, i) => <li key={i} className="text-sm">{item}</li>)}
      </ul>
    )
  }

  // Array of objects — render as a compact table
  if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'object') {
    const allKeys = [...new Set(value.flatMap((obj) => Object.keys(obj)))]
    // Limit columns to keep readable
    const cols = allKeys.slice(0, 8)
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-xs border">
          <thead>
            <tr className="bg-muted/50">
              {cols.map((col) => (
                <th key={col} className="px-2 py-1 text-left font-medium text-muted-foreground whitespace-nowrap">
                  {labelFor(col)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {value.slice(0, 20).map((row, i) => (
              <tr key={i} className="border-t">
                {cols.map((col) => (
                  <td key={col} className="px-2 py-1 whitespace-nowrap max-w-[200px] truncate" title={formatCellValue(row[col])}>
                    {formatCellValue(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {value.length > 20 && (
          <p className="text-xs text-muted-foreground mt-1">Showing 20 of {value.length} rows</p>
        )}
      </div>
    )
  }

  // Plain object — render as key-value pairs
  if (typeof value === 'object' && !Array.isArray(value)) {
    return (
      <dl className="space-y-0.5">
        {Object.entries(value).map(([k, v]) => (
          <div key={k} className="flex gap-2 text-sm">
            <dt className="font-medium text-muted-foreground whitespace-nowrap">{labelFor(k)}:</dt>
            <dd><RenderValue value={v} /></dd>
          </div>
        ))}
      </dl>
    )
  }

  return <span>{String(value)}</span>
}

/** Format a cell value for table display — handles nested objects/arrays. */
function formatCellValue(val) {
  if (val == null) return '-'
  if (typeof val === 'object') {
    if (Array.isArray(val)) return val.map(v => typeof v === 'object' ? JSON.stringify(v) : String(v)).join(', ')
    return Object.entries(val).map(([k, v]) => `${k}: ${v}`).join(', ')
  }
  return typeof val === 'boolean' ? (val ? 'Yes' : 'No') : String(val)
}

export function DossierSection({ sectionKey, facts, dossierData }) {
  const meta = SECTION_META[sectionKey] || { icon: Database, label: labelFor(sectionKey), defaultOpen: false }
  const narrative = dossierData?.[sectionKey]

  // Count displayable items
  const factCount = facts?.length || 0
  const narrativeKeys = narrative && typeof narrative === 'object' && !Array.isArray(narrative)
    ? Object.keys(narrative).length : 0
  const itemCount = factCount + narrativeKeys
  const summary = itemCount > 0 ? `${itemCount} item${itemCount !== 1 ? 's' : ''}` : 'No data'

  // Skip completely empty sections
  if (!narrative && factCount === 0) return null

  return (
    <CollapsibleCard
      icon={meta.icon}
      title={meta.label}
      summary={summary}
      defaultOpen={meta.defaultOpen}
    >
      {/* String narrative (e.g. assessment.organizing_summary at top level) */}
      {narrative && typeof narrative === 'string' && (
        <p className="text-sm whitespace-pre-wrap mb-3">{narrative}</p>
      )}

      {/* Object narrative — render each key/value with smart formatting */}
      {narrative && typeof narrative === 'object' && !Array.isArray(narrative) && (
        <div className="space-y-4 mb-3">
          {Object.entries(narrative).map(([key, val]) => (
            <div key={key}>
              <h4 className="text-sm font-semibold mb-1">{labelFor(key)}</h4>
              <div className="pl-1">
                <RenderValue value={val} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Array narrative (rare, e.g. skipped_tools) */}
      {narrative && Array.isArray(narrative) && (
        <div className="mb-3">
          <RenderValue value={narrative} />
        </div>
      )}

      {/* Facts table from research_facts */}
      {facts && facts.length > 0 && (
        <div className="overflow-x-auto mt-2">
          <h4 className="text-xs font-semibold text-muted-foreground mb-1 uppercase tracking-wide">Verified Facts</h4>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="px-3 py-1.5 text-left font-medium text-xs text-muted-foreground">Attribute</th>
                <th className="px-3 py-1.5 text-left font-medium text-xs text-muted-foreground">Value</th>
                <th className="px-3 py-1.5 text-left font-medium text-xs text-muted-foreground">Source</th>
                <th className="px-3 py-1.5 text-left font-medium text-xs text-muted-foreground">Confidence</th>
                <th className="px-3 py-1.5 text-left font-medium text-xs text-muted-foreground">As Of</th>
              </tr>
            </thead>
            <tbody>
              {facts.map((fact, i) => (
                <FactRow key={`${fact.attribute_name}-${i}`} fact={fact} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </CollapsibleCard>
  )
}
