import { useState } from 'react'
import { Users, AlertTriangle, Loader2 } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Button } from '@/components/ui/button'
import { useMasterExecutives } from '@/shared/api/profile'

// 24Q-7: ExecutivesCard. Surfaces the Mergent executive roster on the
// master profile. Q8 Management coverage moves Medium -> Strong on the
// "who runs this place?" axis.
//
// Data caveats (see endpoint docstring): no compensation, no tenure, no
// prior employer in the loaded schema, and Mergent's data is historical
// (current + former execs interleaved). We rank by title heuristic so
// the top of the list is always the most senior brass.

const VISIBLE_ROWS = 10

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

function formatVintageDate(d) {
  if (!d) return null
  try {
    const parsed = new Date(d)
    if (Number.isNaN(parsed.getTime())) return null
    return parsed.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return null
  }
}

export function ExecutivesCard({ masterId }) {
  const [expanded, setExpanded] = useState(false)
  const { data, isLoading, isError } = useMasterExecutives(masterId)

  if (isLoading) {
    return (
      <CollapsibleCard icon={Users} title="Executive Roster" summary="Loading...">
        <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Loading Mergent executive roster...</span>
        </div>
      </CollapsibleCard>
    )
  }

  if (isError) {
    return (
      <CollapsibleCard icon={Users} title="Executive Roster" summary="Error">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>Could not load Mergent executive roster.</p>
        </div>
      </CollapsibleCard>
    )
  }

  const summary = data?.summary || {}
  const executives = data?.executives || []
  const total = summary.total_executives || 0

  if (!total && executives.length === 0) {
    return (
      <CollapsibleCard icon={Users} title="Executive Roster" summary="No records matched">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No Mergent executive records have been matched to this employer. This does{' '}
            <strong>not</strong> mean the company has no executives &mdash; it may mean our
            matching has not yet connected this employer to Mergent's roster, or the company
            is not in Mergent's coverage.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  const summaryText = `${formatNumber(total)} executive${total === 1 ? '' : 's'}`
  const visibleExecs = expanded ? executives : executives.slice(0, VISIBLE_ROWS)
  const hasMore = executives.length > VISIBLE_ROWS
  const vintageDate = formatVintageDate(data?.source_freshness)

  return (
    <CollapsibleCard icon={Users} title="Executive Roster" summary={summaryText}>
      <div className="space-y-4">
        {/* Note on data caveats. Sort order is title-seniority but we no
            longer surface a rank tally / hierarchy chart on the card --
            the actual title text is what matters to organizers. */}
        <p className="text-xs italic text-muted-foreground">
          Mergent's roster includes both current and former officers. Most senior titles
          (CEO, Chairman, Presidents, C-suite) appear first. No compensation, tenure, or
          prior-employer fields are loaded.
        </p>

        {/* Executive table */}
        {executives.length > 0 && (
          <>
            <div className="overflow-x-auto border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Name</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Title</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleExecs.map((e, i) => (
                    <tr key={`${e.duns}-${i}`} className="border-b">
                      <td className="px-3 py-2 font-medium whitespace-nowrap">{e.name || '\u2014'}</td>
                      <td className="px-3 py-2">{e.title || '\u2014'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {hasMore && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setExpanded((v) => !v)}
              >
                {expanded
                  ? 'Show top 10 only'
                  : `Show all ${executives.length} executives (top by title rank)`}
              </Button>
            )}
            {executives.length < total && (
              <p className="text-xs text-muted-foreground">
                Showing top {executives.length} of {formatNumber(total)} total. Increase{' '}
                <code>limit</code> via API to retrieve more.
              </p>
            )}
          </>
        )}

        {vintageDate && (
          <p className="text-xs text-muted-foreground">
            Mergent data current as of {vintageDate}
          </p>
        )}
      </div>
    </CollapsibleCard>
  )
}
