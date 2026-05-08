import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { FactRow } from './FactRow'
import { labelFor, questionFor, isNotFoundValue } from './questionMap'
import {
  Building2, Users, HardHat, DollarSign, Briefcase, ClipboardCheck, Database,
  CheckCircle, XCircle, MapPin, Crown, Network,
} from 'lucide-react'

const SECTION_META = {
  identity:            { icon: Building2,      label: 'Company Identity',    defaultOpen: true },
  corporate_structure: { icon: Network,        label: 'Corporate Structure', defaultOpen: true },
  locations:           { icon: MapPin,         label: 'Locations',           defaultOpen: false },
  leadership:          { icon: Crown,          label: 'Leadership',          defaultOpen: false },
  labor:               { icon: Users,          label: 'Labor Relations',     defaultOpen: true },
  workforce:           { icon: Briefcase,      label: 'Workforce',           defaultOpen: false },
  workplace:           { icon: HardHat,        label: 'Workplace Safety',    defaultOpen: false },
  financial:           { icon: DollarSign,     label: 'Financial',           defaultOpen: false },
  assessment:          { icon: ClipboardCheck, label: 'Overall Assessment',  defaultOpen: true },
  sources:             { icon: Database,       label: 'Data Sources',        defaultOpen: false },
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

export function DossierSection({ sectionKey, facts, dossierData, onReviewFact, onReviewSection, sectionReviewStatus }) {
  const meta = SECTION_META[sectionKey] || { icon: Database, label: labelFor(sectionKey), defaultOpen: false }
  const narrative = dossierData?.[sectionKey]

  // Count displayable items (exclude not-found facts)
  const realFacts = facts?.filter(f => !isNotFoundValue(f.attribute_value)) || []
  const factCount = realFacts.length
  const narrativeKeys = narrative && typeof narrative === 'object' && !Array.isArray(narrative)
    ? Object.keys(narrative).length : 0
  const itemCount = factCount + narrativeKeys
  const summary = itemCount > 0 ? `${itemCount} item${itemCount !== 1 ? 's' : ''}` : 'No data'

  // Skip completely empty sections
  if (!narrative && factCount === 0) return null

  return (
    <CollapsibleCard
      icon={meta.icon}
      title={`${meta.label}${itemCount > 0 ? ` (${itemCount})` : ''}`}
      summary={summary}
      defaultOpen={meta.defaultOpen}
    >
      {/* Section-level review controls */}
      {onReviewSection && (
        <div className="flex items-center gap-2 mb-3">
          {sectionReviewStatus ? (
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded border ${
              sectionReviewStatus === 'confirmed'
                ? 'bg-[#3a7d44]/15 text-[#3a7d44] border-[#3a7d44]/30'
                : 'bg-[#c23a22]/15 text-[#c23a22] border-[#c23a22]/30'
            }`}>
              {sectionReviewStatus === 'confirmed' ? (
                <><CheckCircle className="h-3 w-3" /> Section Approved</>
              ) : (
                <><XCircle className="h-3 w-3" /> Section Rejected</>
              )}
            </span>
          ) : (
            <>
              <button
                onClick={() => onReviewSection(sectionKey, 'confirmed')}
                className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded border border-transparent text-[#8a7e6d] hover:bg-[#3a7d44]/10 hover:text-[#3a7d44] transition-colors"
                title="Approve all facts in this section"
              >
                <CheckCircle className="h-3 w-3" />
                Approve Section
              </button>
              <button
                onClick={() => onReviewSection(sectionKey, 'rejected')}
                className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded border border-transparent text-[#8a7e6d] hover:bg-[#c23a22]/10 hover:text-[#c23a22] transition-colors"
                title="Reject all facts in this section"
              >
                <XCircle className="h-3 w-3" />
                Reject Section
              </button>
            </>
          )}
        </div>
      )}

      {/* Unified Q&A display: narrative data + structured facts as Q&A cards */}
      <div className="space-y-2">
        {/* String narrative (e.g. assessment summary as a single block) */}
        {narrative && typeof narrative === 'string' && (
          <div className="border-l-4 border-l-[#3a7d44] bg-[#f5f0e8] rounded-r-md p-3 space-y-1">
            <h4 className="text-sm font-medium text-[#2c2417]">{questionFor(sectionKey === 'assessment' ? 'organizing_summary' : sectionKey)}</h4>
            <p className="text-sm whitespace-pre-wrap text-[#2c2417]">{narrative}</p>
          </div>
        )}

        {/* Object narrative — each key becomes a Q&A card */}
        {narrative && typeof narrative === 'object' && !Array.isArray(narrative) &&
          Object.entries(narrative).map(([key, val]) => {
            if (val == null) return null
            const strVal = typeof val === 'string' ? val : ''
            const notFound = typeof val === 'string' && isNotFoundValue(val)
            if (notFound) return null
            return (
              <div key={key} className="border-l-4 border-l-[#3a7d44] bg-[#f5f0e8] rounded-r-md p-3 space-y-1">
                <h4 className="text-sm font-medium text-[#2c2417]">{questionFor(key)}</h4>
                <div className="text-sm text-[#2c2417]">
                  <RenderValue value={val} />
                </div>
                <div className="text-[11px] text-[#8a7e6d]">Source: dossier narrative</div>
              </div>
            )
          })
        }

        {/* Array narrative (rare) */}
        {narrative && Array.isArray(narrative) && (
          <div className="border-l-4 border-l-[#d9cebb] bg-[#f5f0e8] rounded-r-md p-3">
            <RenderValue value={narrative} />
          </div>
        )}

        {/* Structured facts from research_facts — only show real data */}
        {facts && facts.length > 0 && (() => {
          const displayFacts = facts.filter(f => !isNotFoundValue(f.attribute_value))
          return displayFacts.length > 0 ? (
            displayFacts.map((fact, i) => (
              <FactRow key={`fact-${fact.attribute_name}-${i}`} fact={fact} onReview={onReviewFact} />
            ))
          ) : null
        })()}
      </div>
    </CollapsibleCard>
  )
}
