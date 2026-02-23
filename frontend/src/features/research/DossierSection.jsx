import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { FactRow } from './FactRow'
import {
  Building2, Users, Scale, FileText, Landmark, TrendingUp, ClipboardCheck,
} from 'lucide-react'

const SECTION_META = {
  identity: { icon: Building2, label: 'Company Identity', defaultOpen: true },
  labor_relations: { icon: Users, label: 'Labor Relations', defaultOpen: true },
  financial: { icon: TrendingUp, label: 'Financial Standing', defaultOpen: false },
  government: { icon: Landmark, label: 'Government Contracts & Compliance', defaultOpen: false },
  legal: { icon: Scale, label: 'Legal & Regulatory', defaultOpen: false },
  industry: { icon: FileText, label: 'Industry Context', defaultOpen: false },
  assessment: { icon: ClipboardCheck, label: 'Overall Assessment', defaultOpen: true },
}

export function DossierSection({ sectionKey, facts, dossierData }) {
  const meta = SECTION_META[sectionKey] || { icon: FileText, label: sectionKey, defaultOpen: false }
  const summary = facts ? `${facts.length} fact${facts.length !== 1 ? 's' : ''}` : 'No data'

  // Dossier JSON may have a narrative summary for this section
  const narrative = dossierData?.[sectionKey]

  return (
    <CollapsibleCard
      icon={meta.icon}
      title={meta.label}
      summary={summary}
      defaultOpen={meta.defaultOpen}
    >
      {narrative && typeof narrative === 'string' && (
        <p className="text-sm text-muted-foreground mb-3">{narrative}</p>
      )}
      {narrative && typeof narrative === 'object' && !Array.isArray(narrative) && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm mb-3">
          {Object.entries(narrative).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="font-medium text-muted-foreground">{k.replace(/_/g, ' ')}</dt>
              <dd>{typeof v === 'object' ? JSON.stringify(v) : String(v ?? '-')}</dd>
            </div>
          ))}
        </dl>
      )}
      {facts && facts.length > 0 && (
        <div className="overflow-x-auto">
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
      {(!facts || facts.length === 0) && !narrative && (
        <p className="text-sm text-muted-foreground italic">No facts found for this section.</p>
      )}
    </CollapsibleCard>
  )
}
