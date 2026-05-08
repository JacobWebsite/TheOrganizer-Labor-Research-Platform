import { useState } from 'react'
import { Landmark, AlertTriangle, Loader2 } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Button } from '@/components/ui/button'
import { useMasterLobbying } from '@/shared/api/profile'

// 24Q-39: LobbyingCard. Surfaces federal LDA lobbying disclosures on the
// master profile -- "did this firm hire lobbyists, on what issues, and
// for how much?" Q24 Political moves Weak -> Medium (still needs FEC
// indiv24 + state political to reach Strong).
//
// Per UX direction (matches ExecutivesCard / InstitutionalOwnersCard):
// minimal chrome. Quarterly spend timeline + top issues + top registrants.
// No tier badges, no fancy charts, no rank chrome.

const VISIBLE_QUARTERS = 8
const VISIBLE_ISSUES = 5
const VISIBLE_REGISTRANTS = 5

function formatNumber(n) {
  if (n == null) return '—'
  return Number(n).toLocaleString()
}

function formatCurrency(n) {
  if (n == null || n === 0) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(0)}K`
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(n)
}

function formatPeriodShort(period_display, year) {
  if (!period_display) return year ? String(year) : ''
  // "1st Quarter (Jan 1 - Mar 31)" -> "Q1 2024"
  const m = period_display.match(/(\d)(?:st|nd|rd|th)\s+Quarter/i)
  if (m) return `Q${m[1]} ${year}`
  // "Mid-Year" -> "MY 2024"
  if (/mid[- ]?year/i.test(period_display)) return `MY ${year}`
  if (/year[- ]?end/i.test(period_display)) return `YE ${year}`
  return `${period_display} ${year}`
}

export function LobbyingCard({ masterId }) {
  const [expandQuarters, setExpandQuarters] = useState(false)
  const [expandIssues, setExpandIssues] = useState(false)
  const [expandRegistrants, setExpandRegistrants] = useState(false)
  const { data, isLoading, isError } = useMasterLobbying(masterId)

  if (isLoading) {
    return (
      <CollapsibleCard icon={Landmark} title="Federal Lobbying" summary="Loading...">
        <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Loading LDA lobbying data...</span>
        </div>
      </CollapsibleCard>
    )
  }

  if (isError) {
    return (
      <CollapsibleCard icon={Landmark} title="Federal Lobbying" summary="Error">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>Could not load LDA data.</p>
        </div>
      </CollapsibleCard>
    )
  }

  const summary = data?.summary || {}
  const quarterly = data?.quarterly_spend || []
  const issues = data?.top_issues || []
  const registrants = data?.top_registrants || []

  if (!summary.is_matched) {
    return (
      <CollapsibleCard
        icon={Landmark}
        title="Federal Lobbying"
        summary="No LDA registrations found"
      >
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No Lobbying Disclosure Act filings have been matched to this employer. This does{' '}
            <strong>not</strong> mean the firm hasn't lobbied &mdash; it may mean its registered
            client name in the LDA database differs from our canonical name. Foreign-registered
            clients are also outside the current load window.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  if (!summary.total_filings) {
    return (
      <CollapsibleCard icon={Landmark} title="Federal Lobbying" summary="Matched, no filings">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            Matched as LDA client <strong>{summary.client_name_used}</strong> but no filings
            are reported in our load window (last 5 years).
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  const summaryText = `${formatNumber(summary.total_filings)} filing${summary.total_filings === 1 ? '' : 's'} · ${formatCurrency(summary.total_spend)}`
  const visibleQuarters = expandQuarters ? quarterly : quarterly.slice(0, VISIBLE_QUARTERS)
  const visibleIssues = expandIssues ? issues : issues.slice(0, VISIBLE_ISSUES)
  const visibleRegistrants = expandRegistrants ? registrants : registrants.slice(0, VISIBLE_REGISTRANTS)

  return (
    <CollapsibleCard icon={Landmark} title="Federal Lobbying" summary={summaryText}>
      <div className="space-y-4">
        <p className="text-xs italic text-muted-foreground">
          U.S. Senate Lobbying Disclosure Act filings (LD-1, LD-2). Total spend includes both
          registrant-reported income and self-filer-reported expenses for{' '}
          <strong>{summary.client_name_used}</strong>.
          {summary.match_method === 'trigram' && summary.match_confidence != null && (
            <>
              {' '}Client matched by name similarity (confidence{' '}
              {Math.round(summary.match_confidence * 100)}%).
            </>
          )}
        </p>

        {/* Top-line metrics */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.total_filings)}</div>
            <div className="text-xs text-muted-foreground">Filings</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatCurrency(summary.total_spend)}</div>
            <div className="text-xs text-muted-foreground">Total Spend</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.registrants_count)}</div>
            <div className="text-xs text-muted-foreground">Registrants Hired</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.active_quarters)}</div>
            <div className="text-xs text-muted-foreground">Active Quarters</div>
          </div>
        </div>

        {/* Quarterly spend */}
        {quarterly.length > 0 && (
          <div>
            <h4 className="mb-2 text-sm font-medium">Quarterly Spend</h4>
            <div className="overflow-x-auto border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Period</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Filings</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Spend</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleQuarters.map((q) => (
                    <tr key={`${q.year}-${q.period}`} className="border-b">
                      <td className="px-3 py-2">{formatPeriodShort(q.period_display, q.year)}</td>
                      <td className="px-3 py-2 text-right">{formatNumber(q.filings)}</td>
                      <td className="px-3 py-2 text-right">{formatCurrency(q.spend)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {quarterly.length > VISIBLE_QUARTERS && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setExpandQuarters((v) => !v)}
              >
                {expandQuarters ? `Show ${VISIBLE_QUARTERS} most recent` : `Show all ${quarterly.length} quarters`}
              </Button>
            )}
          </div>
        )}

        {/* Top issues */}
        {issues.length > 0 && (
          <div>
            <h4 className="mb-2 text-sm font-medium">Top Issues Lobbied</h4>
            <ul className="space-y-1 text-sm">
              {visibleIssues.map((i) => (
                <li key={i.code} className="flex justify-between">
                  <span>
                    <span className="font-mono text-xs text-muted-foreground">{i.code}</span>{' '}
                    {i.display}
                  </span>
                  <span className="text-muted-foreground">
                    {formatNumber(i.filings)} filing{i.filings === 1 ? '' : 's'}
                  </span>
                </li>
              ))}
            </ul>
            {issues.length > VISIBLE_ISSUES && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setExpandIssues((v) => !v)}
              >
                {expandIssues ? `Show top ${VISIBLE_ISSUES}` : `Show all ${issues.length} issues`}
              </Button>
            )}
          </div>
        )}

        {/* Top registrants */}
        {registrants.length > 0 && (
          <div>
            <h4 className="mb-2 text-sm font-medium">Top Registrants Hired</h4>
            <div className="overflow-x-auto border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Registrant</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">State</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Filings</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Spend</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRegistrants.map((r) => (
                    <tr key={r.registrant_id} className="border-b">
                      <td className="px-3 py-2 font-medium">{r.name}</td>
                      <td className="px-3 py-2 text-xs">{r.state || '—'}</td>
                      <td className="px-3 py-2 text-right">{formatNumber(r.filings)}</td>
                      <td className="px-3 py-2 text-right">{formatCurrency(r.spend)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {registrants.length > VISIBLE_REGISTRANTS && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setExpandRegistrants((v) => !v)}
              >
                {expandRegistrants ? `Show top ${VISIBLE_REGISTRANTS}` : `Show all ${registrants.length} registrants`}
              </Button>
            )}
          </div>
        )}

        {summary.latest_period && (
          <p className="text-xs text-muted-foreground">
            LDA data current through {summary.latest_period}
          </p>
        )}
      </div>
    </CollapsibleCard>
  )
}
