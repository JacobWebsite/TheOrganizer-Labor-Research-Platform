import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useNationalUnionDetail, useUnionSearch } from '@/shared/api/unions'
import { cn } from '@/lib/utils'

function formatNumber(n) {
  if (n == null) return '--'
  return Number(n).toLocaleString()
}

/**
 * Level 2 node: individual locals within a state
 */
function LocalNode({ local }) {
  const navigate = useNavigate()

  return (
    <div
      className="flex items-center justify-between py-1.5 px-3 hover:bg-[#ede7db] cursor-pointer text-sm"
      style={{ paddingLeft: '64px' }}
      onClick={() => navigate(`/unions/${local.f_num}`)}
    >
      <span className="truncate">{local.union_name || `Local ${local.f_num}`}</span>
      <div className="flex items-center gap-4 text-xs text-muted-foreground shrink-0">
        {local.city && <span>{local.city}</span>}
        <span className="w-16 text-right text-[#1a6b5a]">{formatNumber(local.members)}</span>
      </div>
    </div>
  )
}

/**
 * Level 1 node: states within an affiliation
 */
function StateNode({ affAbbr, stateName, stateData }) {
  const [expanded, setExpanded] = useState(false)

  const { data: localsData, isLoading } = useUnionSearch({
    aff_abbr: affAbbr,
    state: stateName,
    limit: 100,
    enabled: expanded,
  })

  const locals = localsData?.unions || []

  return (
    <div>
      <div
        className="flex items-center justify-between py-1.5 px-3 hover:bg-accent/50 cursor-pointer text-sm border-b"
        style={{ paddingLeft: '32px' }}
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <ChevronRight className={cn('h-3.5 w-3.5 text-muted-foreground transition-transform', expanded && 'rotate-90')} />
          <span className="font-medium">{stateName}</span>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>{stateData.local_count || 0} locals</span>
          <span className="w-20 text-right">{formatNumber(stateData.total_members)} members</span>
        </div>
      </div>

      {expanded && (
        <div className="border-l-2 border-l-[#d9cebb] ml-8 pl-0">
          {isLoading && (
            <div className="py-2 text-xs text-muted-foreground pl-8">
              Loading locals...
            </div>
          )}
          {locals.map((local) => (
            <LocalNode key={local.f_num} local={local} />
          ))}
          {!isLoading && locals.length === 0 && (
            <div className="py-2 text-xs text-muted-foreground pl-8">
              No locals found
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Level 0 node: top-level affiliations
 */
function AffiliationNode({ affiliation }) {
  const [expanded, setExpanded] = useState(false)

  const { data: detail, isLoading } = useNationalUnionDetail(affiliation.aff_abbr, { enabled: expanded })

  const byState = detail?.by_state || []

  return (
    <div className="border-b">
      <div
        className="flex items-center justify-between py-2 px-3 hover:bg-accent/50 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <ChevronRight className={cn('h-4 w-4 text-muted-foreground transition-transform', expanded && 'rotate-90')} />
          <span className="font-editorial text-base font-semibold">{affiliation.aff_abbr}</span>
          <span className="text-sm text-muted-foreground truncate max-w-[300px]">{affiliation.name}</span>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground shrink-0">
          <span>{formatNumber(affiliation.total_locals || affiliation.local_count)} locals</span>
          <span className="w-24 text-right">{formatNumber(affiliation.total_members)} members</span>
        </div>
      </div>

      {expanded && (
        <div>
          {isLoading && (
            <div className="py-2 text-xs text-muted-foreground" style={{ paddingLeft: '32px' }}>
              Loading states...
            </div>
          )}
          {byState.map((s) => (
            <StateNode
              key={s.state}
              affAbbr={affiliation.aff_abbr}
              stateName={s.state}
              stateData={s}
            />
          ))}
          {!isLoading && byState.length === 0 && (
            <div className="py-2 text-xs text-muted-foreground" style={{ paddingLeft: '32px' }}>
              No state breakdown available
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Full affiliation hierarchy tree view for the Unions page.
 */
export function AffiliationTree({ affiliations }) {
  if (!affiliations?.length) {
    return (
      <div className="py-8 text-center text-muted-foreground text-sm">
        No affiliation data available
      </div>
    )
  }

  return (
    <div className="border">
      <div className="flex items-center justify-between py-2 px-3 bg-muted/50 border-b text-xs font-medium text-muted-foreground">
        <span>Affiliation</span>
        <div className="flex items-center gap-4">
          <span>Locals</span>
          <span className="w-24 text-right">Members</span>
        </div>
      </div>
      {affiliations.map((aff) => (
        <AffiliationNode key={aff.aff_abbr} affiliation={aff} />
      ))}
    </div>
  )
}
