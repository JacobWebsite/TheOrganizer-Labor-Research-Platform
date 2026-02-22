import { Scale } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

function formatNumber(n) {
  if (n == null) return '—'
  return Number(n).toLocaleString()
}

function formatDate(d) {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return d
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
  if (!result) return <span className="text-muted-foreground">—</span>
  const colorClass = Object.entries(RESULT_COLORS).find(([key]) => result.includes(key))?.[1] || 'bg-muted text-muted-foreground'
  return (
    <span className={cn('inline-flex items-center px-2 py-0.5 text-xs font-medium', colorClass)}>
      {result}
    </span>
  )
}

export function NlrbSection({ nlrb }) {
  if (!nlrb) return null

  const summary = nlrb.summary || {}
  const elections = nlrb.elections || []
  const ulpCases = nlrb.ulp_cases || []

  // If no data at all, hide section
  if (!summary.total_elections && !summary.total_ulp_cases && elections.length === 0 && ulpCases.length === 0) {
    return null
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Scale className="h-5 w-5 text-blue-600" />
          <CardTitle>NLRB Activity</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary stats */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.total_elections)}</div>
            <div className="text-xs text-muted-foreground">Elections</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.wins)}</div>
            <div className="text-xs text-muted-foreground">Wins</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.losses)}</div>
            <div className="text-xs text-muted-foreground">Losses</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.total_ulp_cases)}</div>
            <div className="text-xs text-muted-foreground">ULP Cases</div>
          </div>
        </div>

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
                  {elections.map((el, i) => (
                    <tr key={el.case_number || i} className="border-b">
                      <td className="px-3 py-2 font-mono text-xs">{el.case_number || '—'}</td>
                      <td className="px-3 py-2">{formatDate(el.election_date || el.date_filed)}</td>
                      <td className="px-3 py-2"><ResultBadge result={el.result || el.status} /></td>
                      <td className="px-3 py-2 text-right">{formatNumber(el.voters_eligible || el.unit_size)}</td>
                      <td className="px-3 py-2 truncate max-w-[200px]">{el.union_name || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
                  {ulpCases.map((c, i) => (
                    <tr key={c.case_number || i} className="border-b">
                      <td className="px-3 py-2 font-mono text-xs">{c.case_number || '—'}</td>
                      <td className="px-3 py-2">{formatDate(c.date_filed)}</td>
                      <td className="px-3 py-2">{c.status || '—'}</td>
                      <td className="px-3 py-2 truncate max-w-[250px]">{c.allegation || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
