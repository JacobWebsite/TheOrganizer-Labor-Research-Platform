import { AlertTriangle, Info } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

function formatPercent(n) {
  if (n == null) return '\u2014'
  // Ratio input (0.77) -> percent output (77%)
  return Math.round(Number(n) * 100) + '%'
}

function formatSummaryPercent(n) {
  if (n == null) return '\u2014'
  // Backend nlrb_summary.win_rate is already a percent (e.g. 77.0).
  // Back-compat: if value looks like a ratio (0-1), convert.
  const num = Number(n)
  if (num <= 1 && num >= 0) return Math.round(num * 100) + '%'
  return Math.round(num) + '%'
}

function formatDate(d) {
  if (!d) return '\u2014'
  // Accepts "YYYY-MM-DD" or ISO datetime; outputs "Dec 15, 2023"
  const s = String(d)
  const iso = s.length >= 10 ? s.slice(0, 10) : s
  const parts = iso.split('-')
  if (parts.length !== 3) return s
  const year = Number(parts[0])
  const month = Number(parts[1]) - 1
  const day = Number(parts[2])
  if (Number.isNaN(year) || Number.isNaN(month) || Number.isNaN(day)) return s
  const date = new Date(Date.UTC(year, month, day))
  if (Number.isNaN(date.getTime())) return s
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

/**
 * NLRB elections section with summary stats and a per-employer aggregated table.
 *
 * Accepts either:
 *   - new shape: { list: [...], summary: {...}, electionsSource, electionNote, affiliation }
 *   - legacy shape (object): { elections: [...], summary: {...}, ... }
 *   - legacy shape (array): [...] plus a separate `summary` prop
 */
export function UnionElectionsSection({ elections, summary: summaryProp }) {
  if (!elections && !summaryProp) return null

  // Normalise inputs across old and new shapes.
  let list = []
  let summary = { ...(summaryProp || {}) }
  let electionsSource = null
  let electionNote = null
  let affiliation = null

  if (Array.isArray(elections)) {
    list = elections
  } else if (elections && typeof elections === 'object') {
    list = elections.list || elections.elections || []
    const legacySummary = elections.summary || {}
    // Merge legacy summary under the explicit summary prop so new callers win,
    // but legacy tests / callers that embed summary inside the elections object
    // still render numbers.
    summary = { ...legacySummary, ...summary }
    electionsSource = elections.elections_source || elections.electionsSource || null
    electionNote = elections.election_note || elections.electionNote || null
    affiliation = elections.affiliation || null
  }

  const hasData = (summary && (summary.wins != null || summary.losses != null || summary.total_elections != null))
    || list.length > 0

  if (!hasData) {
    const fallbackNote = electionNote
      || 'No NLRB election data available for this union. This may mean the union has not held NLRB elections recently, the data has not yet been matched, or the union is outside NLRB jurisdiction.'
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="font-editorial text-xl font-semibold">NLRB Elections</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-start gap-2 p-3 bg-[#f5f0e8] border border-[#d9cebb] rounded-md text-sm text-[#2c2418]">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-[#c78c4e]" />
            <span>{fallbackNote}</span>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Ensure sort by latest_election_date DESC (defensive; backend already orders).
  const sortedList = [...list].sort((a, b) => {
    const ad = a?.latest_election_date || ''
    const bd = b?.latest_election_date || ''
    if (ad === bd) return 0
    return ad < bd ? 1 : -1
  })

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="font-editorial text-xl font-semibold">NLRB Elections</CardTitle>
      </CardHeader>
      <CardContent>
        {/* Affiliate source notice */}
        {electionsSource === 'affiliate' && (
          <div className="flex items-start gap-2 p-3 mb-4 bg-[#f5f0e8] border border-[#3a6b8c]/30 rounded-md text-sm text-[#3a6b8c]">
            <Info className="h-4 w-4 shrink-0 mt-0.5" />
            <span>
              Showing elections for other {affiliation || 'affiliated'} locals. This union has no directly matched NLRB elections.
            </span>
          </div>
        )}

        {/* Summary stats */}
        <div className="flex flex-wrap gap-x-8 gap-y-2 mb-4">
          <div>
            <p className="text-2xl font-bold tabular-nums text-[#3a7d44]">{formatNumber(summary.wins)}</p>
            <p className="text-xs text-muted-foreground">Wins</p>
          </div>
          <div>
            <p className="text-2xl font-bold tabular-nums text-[#c23a22]">{formatNumber(summary.losses)}</p>
            <p className="text-xs text-muted-foreground">Losses</p>
          </div>
          <div>
            <p className="text-2xl font-bold tabular-nums">{formatSummaryPercent(summary.win_rate)}</p>
            <p className="text-xs text-muted-foreground">Win rate</p>
          </div>
          {summary.total_elections != null && (
            <div>
              <p className="text-2xl font-bold tabular-nums">{formatNumber(summary.total_elections)}</p>
              <p className="text-xs text-muted-foreground">Total elections</p>
            </div>
          )}
          {summary.unique_employers != null && (
            <div>
              <p className="text-2xl font-bold tabular-nums">{formatNumber(summary.unique_employers)}</p>
              <p className="text-xs text-muted-foreground">Unique employers</p>
            </div>
          )}
        </div>

        {/* Elections table -- one row per employer, aggregated */}
        {sortedList.length > 0 && (
          <div className="overflow-x-auto border border-[#d9cebb] rounded-md">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#d9cebb] bg-[#ede7db]">
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-[#8a7e6b]">Employer</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-[#8a7e6b]">State</th>
                  <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wider text-[#8a7e6b]">Elections</th>
                  <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wider text-[#8a7e6b]">Wins</th>
                  <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wider text-[#8a7e6b]">Losses</th>
                  <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wider text-[#8a7e6b]">Win rate</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-[#8a7e6b]">Latest</th>
                  <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wider text-[#8a7e6b]">Voters</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-[#8a7e6b]">Latest case</th>
                </tr>
              </thead>
              <tbody>
                {sortedList.map((el, idx) => {
                  const isAffiliate = el.is_affiliate_match === true
                  const count = Number(el.election_count) || 0
                  const rowClass = isAffiliate
                    ? 'border-b border-[#d9cebb] border-l-4 border-l-[#3a6b8c] bg-[#faf6ef]'
                    : 'border-b border-[#d9cebb]'
                  return (
                    <tr key={`${el.employer_name}-${el.state}-${idx}`} className={rowClass}>
                      <td className="px-3 py-2 truncate max-w-[260px]">
                        <span className="text-[#2c2418]">{el.employer_name || '\u2014'}</span>
                        {count > 1 && (
                          <Badge className="ml-2 bg-[#c78c4e]/20 text-[#2c2418] text-[10px] px-1.5 py-0 font-medium">
                            {count}x
                          </Badge>
                        )}
                        {isAffiliate && (
                          <Badge className="ml-2 bg-[#3a6b8c]/15 text-[#3a6b8c] text-[10px] px-1.5 py-0">
                            affiliate
                          </Badge>
                        )}
                      </td>
                      <td className="px-3 py-2 text-[#2c2418]">{el.state || '\u2014'}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{formatNumber(el.election_count)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-[#3a7d44]">{formatNumber(el.win_count)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-[#c23a22]">{formatNumber(el.loss_count)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{formatPercent(el.win_rate)}</td>
                      <td className="px-3 py-2 tabular-nums">{formatDate(el.latest_election_date)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{formatNumber(el.total_eligible_voters)}</td>
                      <td className="px-3 py-2 text-xs text-[#8a7e6b] tabular-nums">{el.latest_case_number || '\u2014'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
