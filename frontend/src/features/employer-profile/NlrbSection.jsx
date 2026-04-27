import { useState } from 'react'
import { Scale, AlertTriangle } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { SourceAttribution } from '@/shared/components/SourceAttribution'
import { DataSourceBadge } from '@/shared/components/DataSourceBadge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const VISIBLE_ROWS = 5

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

function formatDate(d) {
  if (!d) return '\u2014'
  try {
    return new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return d
  }
}

function formatVintageDate(d) {
  if (!d) return null
  try {
    const parsed = new Date(d)
    if (Number.isNaN(parsed.getTime())) return null
    return parsed.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return null
  }
}

const RESULT_COLORS = {
  'Certify': 'bg-green-100 text-green-800',
  'Certified': 'bg-green-100 text-green-800',
  'Won': 'bg-green-100 text-green-800',
  'Lost': 'bg-red-100 text-red-800',
  'Dismissed': 'bg-stone-100 text-stone-700',
  'Withdrawn': 'bg-stone-100 text-stone-700',
  'Stipulated': 'bg-blue-100 text-blue-800',
}

function ResultBadge({ result }) {
  if (!result) return <span className="text-muted-foreground">{'\u2014'}</span>
  const colorClass = Object.entries(RESULT_COLORS).find(([key]) => result.includes(key))?.[1] || 'bg-muted text-muted-foreground'
  return (
    <span className={cn('inline-flex items-center px-2 py-0.5 text-xs font-medium', colorClass)}>
      {result}
    </span>
  )
}

export function NlrbSection({ nlrb, sourceAttribution, scorecard, dataSources, docket }) {
  const [electionsExpanded, setElectionsExpanded] = useState(false)
  const [ulpExpanded, setUlpExpanded] = useState(false)
  const [docketExpanded, setDocketExpanded] = useState(false)

  const summary = nlrb?.summary || {}
  const elections = nlrb?.elections || []
  const ulpCases = nlrb?.ulp_cases || []

  // If no data at all, show warning instead of hiding
  if (!nlrb || (!summary.total_elections && !summary.ulp_cases && !summary.total_ulp_cases && elections.length === 0 && ulpCases.length === 0)) {
    return (
      <CollapsibleCard icon={Scale} title="NLRB Activity" summary="No records matched">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No NLRB election or unfair labor practice records have been matched to this employer.
            This does <strong>not</strong> mean no activity exists — it may mean our matching has
            not yet connected this employer to NLRB case records.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  const summaryText = `${formatNumber(summary.total_elections)} elections \u00b7 ${formatNumber(summary.ulp_cases ?? summary.total_ulp_cases)} ULP cases`
  const visibleElections = electionsExpanded ? elections : elections.slice(0, VISIBLE_ROWS)
  const hasMoreElections = elections.length > VISIBLE_ROWS
  const visibleUlp = ulpExpanded ? ulpCases : ulpCases.slice(0, VISIBLE_ROWS)
  const hasMoreUlp = ulpCases.length > VISIBLE_ROWS
  const vintageDate = formatVintageDate(nlrb?.latest_record_date)

  return (
    <CollapsibleCard icon={Scale} title="NLRB Activity" summary={summaryText}>
      <div className="space-y-4">
        <SourceAttribution attribution={sourceAttribution} />
        {dataSources && (
          <DataSourceBadge
            source="NLRB"
            hasFlag={dataSources.has_nlrb}
            hasData={!!(nlrb?.elections?.length > 0 || nlrb?.ulp_cases?.length > 0)}
          />
        )}
        {/* Summary stats */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.total_elections)}</div>
            <div className="text-xs text-muted-foreground">Elections</div>
          </div>
          <div>
            {/* R7-12 (2026-04-27): API returns union_wins / union_losses / ulp_cases. */}
            <div className="text-2xl font-bold">{formatNumber(summary.union_wins ?? summary.wins)}</div>
            <div className="text-xs text-muted-foreground">Wins</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.union_losses ?? summary.losses)}</div>
            <div className="text-xs text-muted-foreground">Losses</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.ulp_cases ?? summary.total_ulp_cases)}</div>
            <div className="text-xs text-muted-foreground">ULP Cases</div>
          </div>
        </div>

        {/* Close election badge */}
        {scorecard?.has_close_election && (
          <div className="flex flex-wrap gap-2">
            <span className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold bg-amber-100 text-amber-800">
              <AlertTriangle className="h-3 w-3" />
              Close Election: Lost by {scorecard.nlrb_closest_margin} vote{scorecard.nlrb_closest_margin !== 1 ? 's' : ''}
            </span>
          </div>
        )}

        {/* Elections table */}
        {elections.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold">Elections</h4>
            <div className="overflow-x-auto border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Case</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Date</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Result</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Voters</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Union</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleElections.map((el, i) => (
                    <tr key={el.case_number || i} className="border-b">
                      <td className="px-3 py-2 font-mono text-xs">{el.case_number || '\u2014'}</td>
                      <td className="px-3 py-2">{formatDate(el.election_date || el.date_filed)}</td>
                      {/* R7-12 (2026-04-27): API returns boolean union_won + eligible_voters. */}
                      <td className="px-3 py-2"><ResultBadge result={el.result || el.status || (el.union_won === true ? 'Won' : el.union_won === false ? 'Lost' : null)} /></td>
                      <td className="px-3 py-2 text-right">{formatNumber(el.eligible_voters ?? el.voters_eligible ?? el.unit_size)}</td>
                      <td className="px-3 py-2 truncate max-w-[200px]">{el.union_name || '\u2014'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {hasMoreElections && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setElectionsExpanded((v) => !v)}
              >
                {electionsExpanded ? 'Show less' : `Show all ${elections.length} elections`}
              </Button>
            )}
          </div>
        )}

        {/* ULP cases table */}
        {ulpCases.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold">Unfair Labor Practice Cases</h4>
            <div className="overflow-x-auto border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Case</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Date Filed</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Status</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Allegation</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleUlp.map((c, i) => (
                    <tr key={c.case_number || i} className="border-b">
                      <td className="px-3 py-2 font-mono text-xs">{c.case_number || '\u2014'}</td>
                      <td className="px-3 py-2">{formatDate(c.date_filed)}</td>
                      <td className="px-3 py-2">{c.status || '\u2014'}</td>
                      <td className="px-3 py-2 truncate max-w-[250px]">{c.allegation || '\u2014'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {hasMoreUlp && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setUlpExpanded((v) => !v)}
              >
                {ulpExpanded ? 'Show less' : `Show all ${ulpCases.length} cases`}
              </Button>
            )}
          </div>
        )}

        {/* Docket Activity sub-section */}
        {docket && docket.summary && docket.summary.cases_with_docket > 0 && (() => {
          const docketSummary = docket.summary
          const docketCases = docket.cases || []
          const visibleDocket = docketExpanded ? docketCases : docketCases.slice(0, VISIBLE_ROWS)
          const hasMoreDocket = docketCases.length > VISIBLE_ROWS

          return (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-semibold">Docket Activity</h4>
                {docketSummary.has_recent_activity && (
                  <span className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-semibold bg-green-100 text-green-800">
                    <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                    Active
                  </span>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                {docketSummary.cases_with_docket} case{docketSummary.cases_with_docket !== 1 ? 's' : ''} with docket data
                {docketSummary.most_recent_date && (
                  <>, most recent activity {formatDate(docketSummary.most_recent_date)}</>
                )}
              </p>
              <div className="overflow-x-auto border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="px-3 py-2 text-left font-medium text-muted-foreground">Case</th>
                      <th className="px-3 py-2 text-left font-medium text-muted-foreground">First Activity</th>
                      <th className="px-3 py-2 text-left font-medium text-muted-foreground">Last Activity</th>
                      <th className="px-3 py-2 text-right font-medium text-muted-foreground">Duration</th>
                      <th className="px-3 py-2 text-right font-medium text-muted-foreground">Entries</th>
                      <th className="px-3 py-2 text-left font-medium text-muted-foreground">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleDocket.map((c, i) => (
                      <tr key={c.case_number || i} className="border-b">
                        <td className="px-3 py-2 font-mono text-xs">{c.case_number || '\u2014'}</td>
                        <td className="px-3 py-2">{formatDate(c.first_activity)}</td>
                        <td className="px-3 py-2">{formatDate(c.last_activity)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {c.duration_days != null ? c.duration_days + 'd' : '\u2014'}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatNumber(c.entry_count)}</td>
                        <td className="px-3 py-2">
                          {c.is_recent ? (
                            <span className="inline-flex items-center px-2 py-0.5 text-xs font-medium bg-green-100 text-green-800">
                              Recent
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
                              Inactive
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {hasMoreDocket && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full"
                  onClick={() => setDocketExpanded((v) => !v)}
                >
                  {docketExpanded ? 'Show less' : `Show all ${docketCases.length} cases`}
                </Button>
              )}
            </div>
          )
        })()}

        {vintageDate && (
          <p className="text-xs text-muted-foreground">
            NLRB data current through {vintageDate}
          </p>
        )}
      </div>
    </CollapsibleCard>
  )
}
