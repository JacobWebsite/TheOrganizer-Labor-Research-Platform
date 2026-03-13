import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useUnionHierarchy, useUnionSearch } from '@/shared/api/unions'
import { cn } from '@/lib/utils'

function formatNumber(n) {
  if (n == null) return '--'
  return Number(n).toLocaleString()
}

/**
 * Leaf node: individual local union
 */
function LocalNode({ local }) {
  const navigate = useNavigate()

  return (
    <div
      className="flex items-center justify-between py-1.5 px-3 hover:bg-[#ede7db] cursor-pointer text-sm"
      style={{ paddingLeft: '64px' }}
      onClick={() => navigate(`/unions/${local.f_num}`)}
    >
      <span className="truncate">
        {local.union_name || local.name || `Local ${local.f_num}`}
        {local.local_number && local.local_number !== '0' && (
          <span className="text-muted-foreground"> Local {local.local_number}</span>
        )}
        {local.is_likely_inactive && <span className="text-xs text-muted-foreground ml-1">(Inactive)</span>}
      </span>
      <div className="flex items-center gap-4 text-xs text-muted-foreground shrink-0">
        {local.city && <span>{local.city}</span>}
        <span className="w-16 text-right text-[#1a6b5a]">{formatNumber(local.members)}</span>
      </div>
    </div>
  )
}

const LEVEL_LABELS = {
  DC: 'District Council', JC: 'Joint Council', CONF: 'Conference',
  D: 'District', C: 'Council', SC: 'State Council',
  SA: 'System Assembly', BCTC: 'Building & Construction Trades Council',
}

/**
 * Intermediate body node (district council, joint council, etc.)
 */
function IntermediateNode({ intermediate }) {
  const [expanded, setExpanded] = useState(false)

  const label = LEVEL_LABELS[intermediate.level_code] || intermediate.level_code

  return (
    <div>
      <div
        className="flex items-center justify-between py-1.5 px-3 hover:bg-accent/50 cursor-pointer text-sm border-b"
        style={{ paddingLeft: '32px' }}
        onClick={() => setExpanded(v => !v)}
      >
        <div className="flex items-center gap-2">
          <ChevronRight className={cn('h-3.5 w-3.5 text-muted-foreground transition-transform', expanded && 'rotate-90')} />
          <span className="font-medium">{intermediate.name}</span>
          <span className="text-xs text-muted-foreground">({label})</span>
          {intermediate.is_likely_inactive && <span className="text-xs text-muted-foreground">(Inactive)</span>}
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>{intermediate.locals_count} locals</span>
          <span className="w-16 text-right text-[#1a6b5a]">{formatNumber(intermediate.members)}</span>
        </div>
      </div>
      {expanded && (
        <div className="border-l-2 border-l-[#d9cebb] ml-8">
          {intermediate.locals.map(local => (
            <LocalNode key={local.f_num} local={local} />
          ))}
          {intermediate.locals.length === 0 && (
            <div className="py-2 text-xs text-muted-foreground" style={{ paddingLeft: '64px' }}>No locals</div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * State group node for orphan locals (not under an intermediate)
 */
function StateNode({ affAbbr, stateName, stateData, locals: preloadedLocals }) {
  const [expanded, setExpanded] = useState(false)

  // If preloaded locals are provided (from hierarchy endpoint), use those
  const useSearch = !preloadedLocals
  const { data: localsData, isLoading } = useUnionSearch({
    aff_abbr: affAbbr,
    state: stateName,
    limit: 100,
    enabled: expanded && useSearch,
  })

  const locals = preloadedLocals || localsData?.unions || []
  const localCount = stateData?.local_count || locals.length
  const totalMembers = stateData?.total_members

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
          <span>{localCount} locals</span>
          {totalMembers != null && (
            <span className="w-20 text-right">{formatNumber(totalMembers)} members</span>
          )}
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
 * Level 0 node: top-level affiliations using hierarchy endpoint
 */
function AffiliationNode({ affiliation }) {
  const [expanded, setExpanded] = useState(false)

  const { data: hierarchy, isLoading } = useUnionHierarchy(affiliation.aff_abbr, { enabled: expanded })

  const intermediates = hierarchy?.intermediates || []
  const orphanByState = hierarchy?.unaffiliated_locals?.by_state || {}
  const orphanStates = Object.keys(orphanByState).sort()

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
          <span className="w-24 text-right">{formatNumber(affiliation.nhq_members ?? affiliation.deduplicated_members ?? affiliation.total_members)} members</span>
        </div>
      </div>

      {expanded && (
        <div>
          {isLoading && (
            <div className="py-2 text-xs text-muted-foreground" style={{ paddingLeft: '32px' }}>
              Loading hierarchy...
            </div>
          )}
          {intermediates.map((inter) => (
            <IntermediateNode key={inter.f_num} intermediate={inter} />
          ))}
          {orphanStates.map((st) => (
            <StateNode
              key={st}
              affAbbr={affiliation.aff_abbr}
              stateName={st}
              stateData={{ local_count: orphanByState[st].length }}
              locals={orphanByState[st]}
            />
          ))}
          {!isLoading && intermediates.length === 0 && orphanStates.length === 0 && (
            <div className="py-2 text-xs text-muted-foreground" style={{ paddingLeft: '32px' }}>
              No hierarchy data available
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
          <span className="w-24 text-right" title="Dues-paying members (LM filings)">Members</span>
        </div>
      </div>
      {affiliations.map((aff) => (
        <AffiliationNode key={aff.aff_abbr} affiliation={aff} />
      ))}
    </div>
  )
}
