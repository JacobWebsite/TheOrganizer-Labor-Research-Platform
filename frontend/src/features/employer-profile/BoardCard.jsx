import { useState } from 'react'
import { Users, AlertTriangle, Loader2, ExternalLink } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Button } from '@/components/ui/button'
import { useMasterBoard } from '@/shared/api/profile'

// 24Q-14: BoardCard. Surfaces the board of directors parsed from SEC DEF14A
// proxy filings + cross-company interlocks (a director who serves on >1
// board). Pairs with ExecutivesCard (24Q-7) for the full Q8/Q10
// management+board view.
//
// UX matches LobbyingCard / FecContributionsCard / InstitutionalOwnersCard:
// minimal chrome, expandable tables, no tier badges. Independent directors
// surface first because lack of independence is the labor-relations red flag
// (interlocked boards = aligned with capital, not workers).

const VISIBLE_DIRECTORS = 8
const VISIBLE_INTERLOCKS = 5

function formatCurrency(n) {
  if (n == null || n === 0) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(0)}K`
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(n)
}

function independenceBadge(isIndependent) {
  if (isIndependent === true) {
    return (
      <span className="rounded bg-emerald-100 px-1.5 py-0.5 font-mono text-[10px] text-emerald-900">
        IND
      </span>
    )
  }
  if (isIndependent === false) {
    return (
      <span className="rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[10px] text-amber-900">
        INSIDE
      </span>
    )
  }
  return (
    <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
      ?
    </span>
  )
}

export function BoardCard({ masterId }) {
  const [expandDirectors, setExpandDirectors] = useState(false)
  const [expandInterlocks, setExpandInterlocks] = useState(false)
  const { data, isLoading, isError } = useMasterBoard(masterId)

  if (isLoading) {
    return (
      <CollapsibleCard icon={Users} title="Board of Directors" summary="Loading...">
        <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Loading board roster...</span>
        </div>
      </CollapsibleCard>
    )
  }

  if (isError) {
    return (
      <CollapsibleCard icon={Users} title="Board of Directors" summary="Error">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>Could not load board roster.</p>
        </div>
      </CollapsibleCard>
    )
  }

  const summary = data?.summary || {}
  const directors = data?.directors || []
  const interlocks = data?.interlocks || []

  if (!summary.is_matched) {
    return (
      <CollapsibleCard
        icon={Users}
        title="Board of Directors"
        summary="No board roster found"
      >
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No board roster has been parsed from SEC DEF14A proxy filings for this
            employer. DEF14A coverage is limited to publicly traded companies that file
            with the SEC; private companies and most non-profits will appear empty here.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  const indPct = summary.director_count
    ? Math.round((summary.independent_count / summary.director_count) * 100)
    : 0
  const summaryText = `${summary.director_count} director${summary.director_count === 1 ? '' : 's'}${
    summary.independent_count > 0 ? ` · ${indPct}% independent` : ''
  }${interlocks.length > 0 ? ` · ${interlocks.length} interlock${interlocks.length === 1 ? '' : 's'}` : ''}`
  const visibleDirectors = expandDirectors ? directors : directors.slice(0, VISIBLE_DIRECTORS)
  const visibleInterlocks = expandInterlocks ? interlocks : interlocks.slice(0, VISIBLE_INTERLOCKS)

  return (
    <CollapsibleCard icon={Users} title="Board of Directors" summary={summaryText}>
      <div className="space-y-4">
        <p className="text-xs italic text-muted-foreground">
          Board roster parsed from the most recent SEC DEF14A proxy filing. "Independent"
          status is per the company's own classification (NYSE/NASDAQ rules); independence
          claims are widely criticized as too lenient. Interlocks surface directors who
          also serve on the board of another tracked company &mdash; a classic capital-aligned
          governance pattern.
        </p>

        {/* Top-line metrics */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <div className="text-2xl font-bold">{summary.director_count}</div>
            <div className="text-xs text-muted-foreground">Directors</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{summary.independent_count}</div>
            <div className="text-xs text-muted-foreground">Independent (claimed)</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{interlocks.length}</div>
            <div className="text-xs text-muted-foreground">Cross-Company Interlocks</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{summary.fiscal_year || '—'}</div>
            <div className="text-xs text-muted-foreground">Fiscal Year</div>
          </div>
        </div>

        {/* Director roster */}
        {directors.length > 0 && (
          <div>
            <h4 className="mb-2 text-sm font-medium">Roster</h4>
            <div className="overflow-x-auto border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Name</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Status</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Age</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Since</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Committees</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Comp</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleDirectors.map((d, i) => (
                    <tr key={`${d.name}-${i}`} className="border-b align-top">
                      <td className="px-3 py-2">
                        <div className="font-medium">{d.name}</div>
                        {d.occupation && (
                          <div className="mt-0.5 text-xs text-muted-foreground">
                            {d.occupation}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2">{independenceBadge(d.is_independent)}</td>
                      <td className="px-3 py-2 text-right">{d.age || '—'}</td>
                      <td className="px-3 py-2 text-right">{d.since_year || '—'}</td>
                      <td className="px-3 py-2 text-xs">
                        {d.committees && d.committees.length > 0
                          ? d.committees.join(', ')
                          : '—'}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {formatCurrency(d.compensation_total)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {directors.length > VISIBLE_DIRECTORS && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setExpandDirectors((v) => !v)}
              >
                {expandDirectors
                  ? `Show ${VISIBLE_DIRECTORS} of ${directors.length}`
                  : `Show all ${directors.length} directors`}
              </Button>
            )}
          </div>
        )}

        {/* Interlocks */}
        {interlocks.length > 0 && (
          <div>
            <h4 className="mb-2 text-sm font-medium">Cross-Company Board Interlocks</h4>
            <div className="overflow-x-auto border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Director</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Also Serves On</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleInterlocks.map((il, i) => (
                    <tr key={`${il.director_name}-${il.other_master_id}-${i}`} className="border-b">
                      <td className="px-3 py-2 font-medium">{il.director_name}</td>
                      <td className="px-3 py-2">
                        {il.other_master_id ? (
                          <a
                            href={`/employer/MASTER-${il.other_master_id}`}
                            className="inline-flex items-center gap-1 text-blue-700 hover:underline"
                          >
                            {il.other_canonical_name || `Master ${il.other_master_id}`}
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        ) : (
                          <span className="text-muted-foreground">
                            {il.other_canonical_name || '—'}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {interlocks.length > VISIBLE_INTERLOCKS && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setExpandInterlocks((v) => !v)}
              >
                {expandInterlocks
                  ? `Show ${VISIBLE_INTERLOCKS} of ${interlocks.length}`
                  : `Show all ${interlocks.length} interlocks`}
              </Button>
            )}
          </div>
        )}

        {(summary.source_url || summary.extracted_at) && (
          <p className="text-xs text-muted-foreground">
            Source:{' '}
            {summary.source_url ? (
              <a
                href={summary.source_url}
                target="_blank"
                rel="noreferrer"
                className="text-blue-700 hover:underline"
              >
                SEC DEF14A filing
              </a>
            ) : (
              'SEC DEF14A filing'
            )}
            {summary.extracted_at && (
              <> &middot; extracted {summary.extracted_at.slice(0, 10)}</>
            )}
            {summary.parse_strategy && <> &middot; via {summary.parse_strategy}</>}
          </p>
        )}
      </div>
    </CollapsibleCard>
  )
}
