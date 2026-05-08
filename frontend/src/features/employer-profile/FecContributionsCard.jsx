import { useState } from 'react'
import { DollarSign, AlertTriangle, Loader2 } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Button } from '@/components/ui/button'
import { useMasterFecContributions } from '@/shared/api/profile'

// 24Q-41: FecContributionsCard. Surfaces FEC PAC contributions + employee
// individual donations on the master profile -- "did this firm or its
// employees give to candidates?" Q24 Political pillar #2 alongside
// LobbyingCard.
//
// Per UX direction (matches LobbyingCard / InstitutionalOwnersCard):
// minimal chrome. Yearly breakdown + top recipients (PAC) + top donors
// (employee). No tier badges.

const VISIBLE_RECIPIENTS = 5
const VISIBLE_DONORS = 5
const VISIBLE_YEARS = 5

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

function partyBadge(party) {
  if (!party) return null
  const code = String(party).toUpperCase().trim()
  // Match the party color convention used elsewhere in the app
  if (code === 'DEM' || code === 'D')
    return <span className="rounded bg-blue-100 px-1.5 py-0.5 font-mono text-[10px] text-blue-900">DEM</span>
  if (code === 'REP' || code === 'R')
    return <span className="rounded bg-red-100 px-1.5 py-0.5 font-mono text-[10px] text-red-900">REP</span>
  return <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{code.slice(0, 3)}</span>
}

export function FecContributionsCard({ masterId }) {
  const [expandRecipients, setExpandRecipients] = useState(false)
  const [expandDonors, setExpandDonors] = useState(false)
  const [expandYears, setExpandYears] = useState(false)
  const { data, isLoading, isError } = useMasterFecContributions(masterId)

  if (isLoading) {
    return (
      <CollapsibleCard icon={DollarSign} title="FEC Contributions" summary="Loading...">
        <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Loading FEC contribution data...</span>
        </div>
      </CollapsibleCard>
    )
  }

  if (isError) {
    return (
      <CollapsibleCard icon={DollarSign} title="FEC Contributions" summary="Error">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>Could not load FEC contribution data.</p>
        </div>
      </CollapsibleCard>
    )
  }

  const summary = data?.summary || {}
  const recipients = data?.top_pac_recipients || []
  const donors = data?.top_employee_donors || []
  const yearly = data?.yearly_breakdown || []

  if (!summary.is_matched) {
    return (
      <CollapsibleCard
        icon={DollarSign}
        title="FEC Contributions"
        summary="No FEC activity found"
      >
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No registered FEC committee or matched employee donations were found for this
            employer. Employee donations are matched by the company's name appearing in the
            donor's <code>employer</code> field on FEC filings &mdash; if employees report a
            different name (e.g. a subsidiary or DBA), donations may be missed here.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  const totalDollars =
    (summary.pac_dollars_total || 0) + (summary.employee_dollars_total || 0)
  const summaryText = `${formatNumber((summary.employee_donations_count || 0))} donation${summary.employee_donations_count === 1 ? '' : 's'} · ${formatCurrency(totalDollars)}`
  const visibleRecipients = expandRecipients ? recipients : recipients.slice(0, VISIBLE_RECIPIENTS)
  const visibleDonors = expandDonors ? donors : donors.slice(0, VISIBLE_DONORS)
  const visibleYears = expandYears ? yearly : yearly.slice(0, VISIBLE_YEARS)

  return (
    <CollapsibleCard icon={DollarSign} title="FEC Contributions" summary={summaryText}>
      <div className="space-y-4">
        <p className="text-xs italic text-muted-foreground">
          Federal Election Commission contributions: PAC contributions are donations FROM the
          firm's affiliated political committee TO candidates. Employee donations are
          contributions BY individuals naming this firm as their employer. Variants tried:{' '}
          {(summary.employer_norms_used || []).join(', ') || '—'}.
        </p>

        {/* Top-line metrics */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.pac_committees_count)}</div>
            <div className="text-xs text-muted-foreground">PAC Committees</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatCurrency(summary.pac_dollars_total)}</div>
            <div className="text-xs text-muted-foreground">PAC $ Given</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.employee_donations_count)}</div>
            <div className="text-xs text-muted-foreground">Employee Donations</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatCurrency(summary.employee_dollars_total)}</div>
            <div className="text-xs text-muted-foreground">Employee $ Given</div>
          </div>
        </div>

        {/* Yearly breakdown */}
        {yearly.length > 0 && (
          <div>
            <h4 className="mb-2 text-sm font-medium">Annual Activity</h4>
            <div className="overflow-x-auto border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Year</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">PAC $</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Employee $</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleYears.map((y) => (
                    <tr key={y.year} className="border-b">
                      <td className="px-3 py-2 font-medium">{y.year}</td>
                      <td className="px-3 py-2 text-right">{formatCurrency(y.pac_dollars)}</td>
                      <td className="px-3 py-2 text-right">{formatCurrency(y.employee_dollars)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {yearly.length > VISIBLE_YEARS && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setExpandYears((v) => !v)}
              >
                {expandYears ? `Show ${VISIBLE_YEARS} most recent` : `Show all ${yearly.length} years`}
              </Button>
            )}
          </div>
        )}

        {/* Top PAC recipients */}
        {recipients.length > 0 && (
          <div>
            <h4 className="mb-2 text-sm font-medium">Top PAC Recipients</h4>
            <div className="overflow-x-auto border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Candidate</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Party</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Office</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Donations</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRecipients.map((r) => (
                    <tr key={r.cand_id} className="border-b">
                      <td className="px-3 py-2 font-medium">{r.name || r.cand_id}</td>
                      <td className="px-3 py-2">{partyBadge(r.party)}</td>
                      <td className="px-3 py-2 text-xs">
                        {r.office || '—'}
                        {r.state ? <span className="ml-1 text-muted-foreground">({r.state})</span> : null}
                      </td>
                      <td className="px-3 py-2 text-right">{formatNumber(r.contributions)}</td>
                      <td className="px-3 py-2 text-right">{formatCurrency(r.dollars)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {recipients.length > VISIBLE_RECIPIENTS && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setExpandRecipients((v) => !v)}
              >
                {expandRecipients
                  ? `Show top ${VISIBLE_RECIPIENTS}`
                  : `Show all ${recipients.length} recipients`}
              </Button>
            )}
          </div>
        )}

        {/* Top employee donors */}
        {donors.length > 0 && (
          <div>
            <h4 className="mb-2 text-sm font-medium">Top Employee Donors</h4>
            <div className="overflow-x-auto border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Name</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Occupation</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Location</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Donations</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleDonors.map((d, i) => (
                    <tr key={`${d.name}-${i}`} className="border-b">
                      <td className="px-3 py-2 font-medium">{d.name}</td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">{d.occupation || '—'}</td>
                      <td className="px-3 py-2 text-xs">
                        {d.city ? `${d.city}, ${d.state}` : (d.state || '—')}
                      </td>
                      <td className="px-3 py-2 text-right">{formatNumber(d.contributions)}</td>
                      <td className="px-3 py-2 text-right">{formatCurrency(d.dollars)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {donors.length > VISIBLE_DONORS && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setExpandDonors((v) => !v)}
              >
                {expandDonors
                  ? `Show top ${VISIBLE_DONORS}`
                  : `Show all ${donors.length} donors`}
              </Button>
            )}
          </div>
        )}

        {(summary.latest_pac_date || summary.latest_employee_date) && (
          <p className="text-xs text-muted-foreground">
            FEC data current through{' '}
            {summary.latest_employee_date || summary.latest_pac_date}
          </p>
        )}
      </div>
    </CollapsibleCard>
  )
}
