import { useState } from 'react'
import { Network, AlertTriangle, TrendingUp, MapPin } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Button } from '@/components/ui/button'
import {
  useEmployerFamilyRollup,
  useEmployerFamilyRollupForF7,
} from '@/shared/api/profile'

/*
 * FamilyRollupSection
 *
 * Aggregates NLRB / OSHA / WHD / F-7 data across all name-variant siblings of
 * the given master_id. Solves the "Starbucks has 380 masters but only 2 show
 * direct linkage to the canonical parent" problem at the UI layer: an organizer
 * searching Starbucks now sees the full national footprint (2,351 cases /
 * 791 elections / 669 wins / 44 F-7 states) instead of the sliver.
 *
 * Only renders when the master has a meaningful family (master_count > 5 OR
 * NLRB cases aggregated > 20). For typical single-location employers it stays
 * hidden because the default NlrbSection already covers them.
 */

const FAMILY_THRESHOLD_MASTERS = 5
const FAMILY_THRESHOLD_NLRB_CASES = 20

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

function formatDate(d) {
  if (!d) return '\u2014'
  try {
    return new Date(d).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return d
  }
}

function StatTile({ label, value, sublabel, tone = 'neutral' }) {
  const toneClasses = {
    neutral: 'border-stone-300 bg-stone-50',
    union: 'border-green-300 bg-green-50',
    enforcement: 'border-amber-300 bg-amber-50',
    warning: 'border-red-300 bg-red-50',
  }
  return (
    <div className={`border p-3 ${toneClasses[tone] || toneClasses.neutral}`}>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
      {sublabel && (
        <div className="mt-0.5 text-xs text-muted-foreground">{sublabel}</div>
      )}
    </div>
  )
}

export function FamilyRollupSection({ masterId, f7Id }) {
  const [electionsExpanded, setElectionsExpanded] = useState(false)
  const [variantsExpanded, setVariantsExpanded] = useState(false)
  // Exactly one of (masterId, f7Id) is expected. masterId has priority.
  const masterQuery = useEmployerFamilyRollup(masterId, {
    enabled: !!masterId,
    limit: 50,
  })
  const f7Query = useEmployerFamilyRollupForF7(f7Id, {
    enabled: !!f7Id && !masterId,
    limit: 50,
  })
  const active = masterId ? masterQuery : f7Query
  const { data, isLoading, isError, error } = active

  if (!masterId && !f7Id) return null

  if (isLoading) {
    return (
      <CollapsibleCard
        title="Corporate Family Rollup"
        icon={Network}
        defaultOpen={false}
      >
        <div className="p-4 text-sm text-muted-foreground">Loading family-rollup data...</div>
      </CollapsibleCard>
    )
  }

  if (isError) {
    return (
      <CollapsibleCard
        title="Corporate Family Rollup"
        icon={Network}
        defaultOpen={false}
      >
        <div className="p-4 text-sm text-red-600">
          Failed to load family rollup: {error?.message || 'unknown error'}
        </div>
      </CollapsibleCard>
    )
  }

  if (!data || data.error) return null

  const masterCount = data.master_count ?? 0
  const nlrb = data.nlrb || {}
  const totals = nlrb.totals || {}
  const elections = nlrb.elections_summary || {}
  const cases = totals.total ?? 0

  // Only show if this employer has a non-trivial family
  if (masterCount < FAMILY_THRESHOLD_MASTERS && cases < FAMILY_THRESHOLD_NLRB_CASES) {
    return null
  }

  const byYear = nlrb.elections_by_year || []
  const byState = (nlrb.elections_by_state || []).filter((s) => s.state)
  const recent = nlrb.recent_elections || []
  const allegations = nlrb.allegations_by_section || []
  const variants = nlrb.respondent_variants || []
  const osha = data.osha?.totals || {}
  const f7 = data.f7 || {}
  const whd = data.whd?.totals || {}

  return (
    <CollapsibleCard
      title={`Corporate Family Rollup \u2014 ${data.family_stem || ''}`.trim()}
      icon={Network}
      defaultOpen={true}
    >
      <div className="space-y-4 p-4">
        {/* Banner explaining the rollup */}
        <div className="flex items-start gap-3 border border-blue-300 bg-blue-50 p-3">
          <AlertTriangle className="h-5 w-5 flex-shrink-0 text-blue-700" />
          <div className="text-sm text-blue-900">
            <div className="font-medium">
              This employer has {formatNumber(masterCount)} variant records across our data sources.
            </div>
            <div className="mt-1 text-xs">
              NLRB, OSHA, and WHD cases are often filed under parent, sibling, or d/b/a
              entity names. The canonical-master row alone undercounts. This block aggregates
              across all name-variant siblings so you see the full corporate family picture.
              Match pattern used: <code className="rounded bg-white px-1">
                {data.match_pattern}
              </code>
            </div>
          </div>
        </div>

        {/* Headline tiles */}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile
            label="NLRB cases"
            value={formatNumber(cases)}
            sublabel={`${formatNumber(totals.rc)} RC \u00B7 ${formatNumber(totals.ca)} CA \u00B7 ${formatNumber(totals.cb)} CB`}
            tone="enforcement"
          />
          <StatTile
            label="Elections"
            value={formatNumber(elections.total_elections)}
            sublabel={
              elections.total_elections
                ? `${formatNumber(elections.union_won)} won \u00B7 ${elections.win_rate_pct}% win rate`
                : null
            }
            tone="union"
          />
          <StatTile
            label="OSHA establishments"
            value={formatNumber(osha.establishments)}
            sublabel={`${formatNumber(osha.states_covered)} states \u00B7 ${formatNumber(osha.total_inspections)} inspections`}
            tone="enforcement"
          />
          <StatTile
            label="F-7 union locals"
            value={formatNumber(f7.locals_count)}
            sublabel={`${formatNumber(f7.states_covered)} states covered`}
            tone="union"
          />
        </div>

        {/* Date range line */}
        {totals.earliest && totals.latest && (
          <div className="text-xs text-muted-foreground">
            NLRB coverage: {formatDate(totals.earliest)} through {formatDate(totals.latest)}
          </div>
        )}

        {/* Elections by year */}
        {byYear.length > 0 && (
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-medium">
              <TrendingUp className="h-4 w-4" /> Elections by year
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="py-1.5 pr-4">Year</th>
                    <th className="py-1.5 pr-4 text-right">Total</th>
                    <th className="py-1.5 pr-4 text-right">Won</th>
                    <th className="py-1.5 pr-4 text-right">Lost</th>
                    <th className="py-1.5 pr-4 text-right">Win %</th>
                  </tr>
                </thead>
                <tbody>
                  {byYear.map((y) => {
                    const pct = y.total ? Math.round((100 * y.won) / y.total) : 0
                    return (
                      <tr key={y.year} className="border-b">
                        <td className="py-1.5 pr-4 font-medium">{y.year}</td>
                        <td className="py-1.5 pr-4 text-right">{formatNumber(y.total)}</td>
                        <td className="py-1.5 pr-4 text-right text-green-700">
                          {formatNumber(y.won)}
                        </td>
                        <td className="py-1.5 pr-4 text-right text-red-700">
                          {formatNumber(y.lost)}
                        </td>
                        <td className="py-1.5 pr-4 text-right">{pct}%</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Elections by state */}
        {byState.length > 0 && (
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-medium">
              <MapPin className="h-4 w-4" /> Elections by state (top {Math.min(byState.length, 12)})
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="py-1.5 pr-4">State</th>
                    <th className="py-1.5 pr-4 text-right">Elections</th>
                    <th className="py-1.5 pr-4 text-right">Won</th>
                    <th className="py-1.5 pr-4 text-right">Lost</th>
                  </tr>
                </thead>
                <tbody>
                  {byState.slice(0, 12).map((s) => (
                    <tr key={s.state} className="border-b">
                      <td className="py-1.5 pr-4 font-medium">{s.state}</td>
                      <td className="py-1.5 pr-4 text-right">{formatNumber(s.elections)}</td>
                      <td className="py-1.5 pr-4 text-right text-green-700">
                        {formatNumber(s.won)}
                      </td>
                      <td className="py-1.5 pr-4 text-right text-red-700">
                        {formatNumber(s.lost)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Top allegations */}
        {allegations.length > 0 && (
          <div>
            <div className="mb-2 text-sm font-medium">Top ULP allegation sections</div>
            <div className="flex flex-wrap gap-2">
              {allegations.slice(0, 8).map((a) => (
                <div
                  key={a.section}
                  className="border border-amber-300 bg-amber-50 px-2 py-1 text-xs"
                >
                  <span className="font-mono font-medium">{a.section}</span>
                  <span className="ml-2 text-muted-foreground">
                    {formatNumber(a.n)} allegations \u00B7 {formatNumber(a.distinct_cases)} cases
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent elections */}
        {recent.length > 0 && (
          <div>
            <div className="mb-2 flex items-center justify-between">
              <div className="text-sm font-medium">
                Recent elections ({electionsExpanded ? recent.length : Math.min(recent.length, 10)})
              </div>
              {recent.length > 10 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setElectionsExpanded(!electionsExpanded)}
                >
                  {electionsExpanded ? 'Show fewer' : `Show all ${recent.length}`}
                </Button>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="py-1.5 pr-3">Date</th>
                    <th className="py-1.5 pr-3">Case</th>
                    <th className="py-1.5 pr-3">Result</th>
                    <th className="py-1.5 pr-3 text-right">Margin</th>
                    <th className="py-1.5 pr-3 text-right">Votes</th>
                    <th className="py-1.5 pr-3">Respondent</th>
                  </tr>
                </thead>
                <tbody>
                  {(electionsExpanded ? recent : recent.slice(0, 10)).map((e, idx) => (
                    <tr key={`${e.case_number}-${idx}`} className="border-b">
                      <td className="py-1.5 pr-3 font-mono text-xs">{formatDate(e.election_date)}</td>
                      <td className="py-1.5 pr-3 font-mono text-xs">
                        {e.case_docket_url ? (
                          <a
                            href={e.case_docket_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary underline hover:no-underline"
                          >
                            {e.case_number}
                          </a>
                        ) : (
                          e.case_number
                        )}
                      </td>
                      <td className="py-1.5 pr-3">
                        {e.union_won === true ? (
                          <span className="text-green-700">Won</span>
                        ) : e.union_won === false ? (
                          <span className="text-red-700">Lost</span>
                        ) : (
                          '\u2014'
                        )}
                      </td>
                      <td className="py-1.5 pr-3 text-right">
                        {e.vote_margin != null ? formatNumber(e.vote_margin) : '\u2014'}
                      </td>
                      <td className="py-1.5 pr-3 text-right">
                        {formatNumber(e.total_votes)} / {formatNumber(e.eligible_voters)}
                      </td>
                      <td className="py-1.5 pr-3 text-xs text-muted-foreground">
                        {(e.respondent_names || '').slice(0, 60)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Respondent name variants -- the "NLRB linkage gap" surfaced directly */}
        {variants.length > 0 && (
          <div>
            <div className="mb-2 flex items-center justify-between">
              <div className="text-sm font-medium">
                Respondent name variants ({variantsExpanded ? variants.length : Math.min(variants.length, 8)})
              </div>
              {variants.length > 8 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setVariantsExpanded(!variantsExpanded)}
                >
                  {variantsExpanded ? 'Show fewer' : `Show all ${variants.length}`}
                </Button>
              )}
            </div>
            <div className="rounded border border-stone-200 bg-stone-50 p-3 text-xs">
              <div className="mb-2 text-muted-foreground">
                Each distinct respondent name is a separate NLRB filing. This list is the direct
                evidence that master-id linkage alone would undercount the employer.
              </div>
              <table className="w-full font-mono">
                <tbody>
                  {(variantsExpanded ? variants : variants.slice(0, 8)).map((v) => (
                    <tr key={v.participant_name} className="border-b border-stone-200 last:border-0">
                      <td className="py-1 pr-3 break-all">{v.participant_name}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{formatNumber(v.cases)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* WHD summary if meaningful */}
        {whd.cases > 0 && (
          <div className="rounded border border-stone-200 bg-stone-50 p-3 text-sm">
            <div className="font-medium">WHD wage-and-hour summary</div>
            <div className="mt-1 text-xs text-muted-foreground">
              {formatNumber(whd.cases)} cases \u00B7 {formatNumber(whd.distinct_legal_names)} legal names \u00B7
              ${formatNumber(Math.round(Number(whd.total_back_wages || 0)))} back wages \u00B7
              {formatNumber(whd.states_covered)} states covered \u00B7
              {formatDate(whd.earliest)} through {formatDate(whd.latest)}
            </div>
          </div>
        )}
      </div>
    </CollapsibleCard>
  )
}
