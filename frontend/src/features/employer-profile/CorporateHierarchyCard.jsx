import { Building2 } from 'lucide-react'
import { useState } from 'react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { SourceAttribution } from '@/shared/components/SourceAttribution'
import { useEmployerCorporate } from '@/shared/api/profile'
import { Button } from '@/components/ui/button'

export function CorporateHierarchyCard({ employerId, sourceAttribution }) {
  const { data, isLoading } = useEmployerCorporate(employerId)
  const [showAllSubs, setShowAllSubs] = useState(false)

  if (isLoading) return null
  if (!data?.ultimate_parent && !data?.parent_chain?.length && !data?.subsidiaries?.length) return null

  const parent = data.ultimate_parent
  const chain = data.parent_chain || []
  const siblings = data.siblings || []
  const subsidiaries = data.subsidiaries || []
  const familyStatus = data.family_union_status || {}
  const displaySubs = showAllSubs ? subsidiaries : subsidiaries.slice(0, 5)

  const totalFamily = (chain.length || 0) + (siblings.length || 0) + (subsidiaries.length || 0) + 1
  const summaryParts = []
  if (parent?.name) summaryParts.push(`Parent: ${parent.name}`)
  summaryParts.push(`${totalFamily} family members`)
  if (familyStatus.unionized_count) summaryParts.push(`${familyStatus.unionized_count} unionized`)

  return (
    <CollapsibleCard
      icon={Building2}
      title="Corporate Hierarchy"
      summary={summaryParts.join(' · ')}
    >
      <div className="space-y-4">
        <SourceAttribution attribution={sourceAttribution} />
        {parent && (
          <div className="text-sm">
            <span className="text-muted-foreground">Ultimate Parent</span>
            <div className="font-medium">
              {parent.name}
              {parent.ticker && <span className="ml-1 text-xs text-muted-foreground">({parent.ticker})</span>}
            </div>
          </div>
        )}

        {chain.length > 0 && (
          <div className="text-sm space-y-1">
            <span className="text-muted-foreground">Parent Chain</span>
            {chain.map((p, i) => (
              <div key={i} className="font-medium" style={{ paddingLeft: `${i * 16}px` }}>
                {'\u2192'} {p.name}
              </div>
            ))}
          </div>
        )}

        {subsidiaries.length > 0 && (
          <div>
            <span className="text-sm text-muted-foreground mb-2 block">Subsidiaries</span>
            <div className="overflow-x-auto border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-2 py-1.5 text-left font-medium">Name</th>
                    <th className="px-2 py-1.5 text-left font-medium">State</th>
                    <th className="px-2 py-1.5 text-right font-medium">Workers</th>
                    <th className="px-2 py-1.5 text-left font-medium">Union</th>
                  </tr>
                </thead>
                <tbody>
                  {displaySubs.map((s, i) => (
                    <tr key={i} className="border-b">
                      <td className="px-2 py-1.5 font-medium">{s.name}</td>
                      <td className="px-2 py-1.5">{s.state || '--'}</td>
                      <td className="px-2 py-1.5 text-right">{s.workers ? Number(s.workers).toLocaleString() : '--'}</td>
                      <td className="px-2 py-1.5">{s.union_name || <span className="text-muted-foreground">--</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {subsidiaries.length > 5 && !showAllSubs && (
              <Button variant="outline" size="sm" className="mt-2" onClick={() => setShowAllSubs(true)}>
                Show all {subsidiaries.length} subsidiaries
              </Button>
            )}
          </div>
        )}

        {(familyStatus.total_family || totalFamily > 1) && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm border-t pt-3">
            <div>
              <span className="text-muted-foreground">Family Size</span>
              <div className="font-medium">{familyStatus.total_family || totalFamily}</div>
            </div>
            {familyStatus.total_workers != null && (
              <div>
                <span className="text-muted-foreground">Total Workers</span>
                <div className="font-medium">{Number(familyStatus.total_workers).toLocaleString()}</div>
              </div>
            )}
            {familyStatus.states_count != null && (
              <div>
                <span className="text-muted-foreground">States</span>
                <div className="font-medium">{familyStatus.states_count}</div>
              </div>
            )}
            {familyStatus.unionized_count != null && (
              <div>
                <span className="text-muted-foreground">Unionized</span>
                <div className="font-medium">{familyStatus.unionized_count}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </CollapsibleCard>
  )
}
