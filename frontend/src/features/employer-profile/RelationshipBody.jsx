import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Button } from '@/components/ui/button'

// Shared body for SuppliersCard / CustomersCard / DistributionCard
// (24Q-16/17/19). Owns the loading / error / empty / populated states
// + the confidence-chip + stale-warning + view-all chrome. Each
// per-card file just wires the icon, title, hook output, and copy.
//
// Contract assumed from `data`:
//   {
//     items: [{
//       child_master_id: int|null,
//       name: str,
//       confidence: float,
//       match_method: 'exact'|'trigram'|'alias'|'unmatched',
//       source_filing: { cik, accession_number, filing_date|null }|null,
//       context: str|null,
//     }],
//     total_extracted: int,
//     total_matched: int,
//     stale: bool,
//     as_of: 'YYYY-MM-DD'|null,
//   }
//
// Codes defensively for empty `items` and missing fields -- the API
// agent is building the endpoint in parallel and the contract may
// change in non-breaking ways before launch.

const VISIBLE_DEFAULT = 10
const VISIBLE_EXPANDED = 20

function confidenceChip(method, confidence) {
  // GREEN >= 0.95, YELLOW 0.85-0.95, GRAY < 0.85 or 'unmatched'.
  // Tailwind hex colors keep us inside the Aged Broadsheet palette.
  let cls = 'bg-[#d9cebb] text-[#2c2418]' // gray (low / unmatched)
  let label = method === 'unmatched' ? 'unmatched' : 'low'
  const pct = confidence != null ? Math.round(confidence * 100) : null

  if (method === 'unmatched' || confidence == null) {
    cls = 'bg-[#d9cebb] text-[#2c2418]'
    label = pct != null ? `${pct}%` : 'unmatched'
  } else if (confidence >= 0.95) {
    cls = 'bg-[#3a7d44] text-[#faf6ef]'
    label = `${pct}%`
  } else if (confidence >= 0.85) {
    cls = 'bg-[#c78c4e] text-[#2c2418]'
    label = `${pct}%`
  } else {
    cls = 'bg-[#d9cebb] text-[#2c2418]'
    label = `${pct}%`
  }

  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] ${cls}`}
      title={`Match method: ${method || 'unknown'}${pct != null ? ` (${pct}%)` : ''}`}
    >
      {label}
    </span>
  )
}

function formatFilingDate(d) {
  if (!d) return null
  // API emits DATE values as 'YYYY-MM-DD'. `new Date('YYYY-MM-DD')` parses
  // as UTC midnight; in US time zones that displays as the previous day.
  // Anchor to local midnight by constructing from parts.
  try {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(d))
    if (m) {
      const parsed = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
      if (!Number.isNaN(parsed.getTime())) {
        return parsed.toLocaleDateString('en-US', {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
        })
      }
    }
    // Fallback for any non-date-only value the API might emit later.
    const parsed = new Date(d)
    if (Number.isNaN(parsed.getTime())) return d
    return parsed.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return d
  }
}

function formatNumber(n) {
  if (n == null) return '-'
  return Number(n).toLocaleString()
}

function latestFilingDate(items) {
  let max = null
  for (const it of items || []) {
    const d = it?.source_filing?.filing_date
    if (!d) continue
    if (max == null || d > max) max = d
  }
  return max
}

export function RelationshipBody({
  icon,
  title,
  data,
  isLoading,
  isError,
  onRetry,
  expanded,
  onToggle,
  emptyText,
  caveatText,
  LoaderIcon,
  AlertIcon,
  LinkIcon,
}) {
  if (isLoading) {
    return (
      <CollapsibleCard icon={icon} title={title} summary="Loading...">
        <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
          {LoaderIcon && <LoaderIcon className="h-4 w-4 animate-spin" />}
          <span>Loading 10-K relationships...</span>
        </div>
        {/* Skeleton rows so the layout doesn't snap when data lands. */}
        <div className="space-y-1 px-3 pb-3" data-testid="relationship-skeleton">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-6 w-full animate-pulse rounded bg-[#ede7db]" />
          ))}
        </div>
      </CollapsibleCard>
    )
  }

  if (isError) {
    return (
      <CollapsibleCard icon={icon} title={title} summary="Error">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {AlertIcon && (
            <AlertIcon className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          )}
          <div className="flex-1">
            <p>Could not load 10-K relationships.</p>
            {onRetry && (
              <Button
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={() => onRetry()}
              >
                Retry
              </Button>
            )}
          </div>
        </div>
      </CollapsibleCard>
    )
  }

  const items = Array.isArray(data?.items) ? data.items : []
  const totalExtracted = data?.total_extracted ?? items.length
  const totalMatched =
    data?.total_matched ?? items.filter((it) => it?.child_master_id != null).length
  const isStale = data?.stale === true
  const asOf = data?.as_of || null
  const latestFiling = latestFilingDate(items) || asOf

  if (items.length === 0) {
    return (
      <CollapsibleCard icon={icon} title={title} summary="None found">
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">{emptyText}</p>
          {isStale && (
            <div className="flex items-start gap-2 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900">
              {AlertIcon && (
                <AlertIcon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-amber-600" />
              )}
              <span>Stale: most recent 10-K is more than two years old.</span>
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            Source: 10-K text mining
            {latestFiling ? ` | latest filing ${formatFilingDate(latestFiling)}` : ''}
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  // Sort defensively: API should already do this, but if it doesn't, we
  // promise the user "top by confidence" so we sort here too. nullish
  // confidences sink.
  const sorted = [...items].sort((a, b) => {
    const av = a?.confidence ?? -1
    const bv = b?.confidence ?? -1
    return bv - av
  })

  const visible = expanded
    ? sorted.slice(0, VISIBLE_EXPANDED)
    : sorted.slice(0, VISIBLE_DEFAULT)
  const hasMore = sorted.length > VISIBLE_DEFAULT

  const summaryText =
    `${formatNumber(totalMatched)} matched | ${formatNumber(totalExtracted)} mentioned` +
    (isStale ? ' | stale' : '')

  return (
    <CollapsibleCard icon={icon} title={title} summary={summaryText}>
      <div className="space-y-3">
        <p className="text-xs italic text-muted-foreground">{caveatText}</p>

        {isStale && (
          <div
            className="flex items-start gap-2 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900"
            data-testid="stale-warning"
          >
            {AlertIcon && (
              <AlertIcon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-amber-600" />
            )}
            <span>
              Stale: most recent 10-K is more than two years old. The relationships
              below may have changed.
            </span>
          </div>
        )}

        <div className="overflow-x-auto border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                  Name
                </th>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                  Confidence
                </th>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                  Context
                </th>
              </tr>
            </thead>
            <tbody>
              {visible.map((it, i) => {
                const linked = it?.child_master_id != null
                const key = `${it?.child_master_id ?? 'unmatched'}-${it?.name ?? ''}-${i}`
                return (
                  <tr key={key} className="border-b">
                    <td className="px-3 py-2 font-medium">
                      {linked ? (
                        <a
                          href={`/employers/MASTER-${it.child_master_id}`}
                          className="inline-flex items-center gap-1 text-blue-700 hover:underline"
                          title={`Open ${it.name}'s master profile`}
                        >
                          {it.name || '-'}
                          {LinkIcon && <LinkIcon className="h-3 w-3" />}
                        </a>
                      ) : (
                        <span className="text-foreground">{it?.name || '-'}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {confidenceChip(it?.match_method, it?.confidence)}
                    </td>
                    <td
                      className="px-3 py-2 text-xs text-muted-foreground"
                      title={it?.context || undefined}
                    >
                      {it?.context
                        ? it.context.length > 80
                          ? `${it.context.slice(0, 80)}...`
                          : it.context
                        : '-'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {hasMore && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full"
            onClick={onToggle}
          >
            {expanded
              ? `Show top ${VISIBLE_DEFAULT}`
              : `View all ${Math.min(sorted.length, VISIBLE_EXPANDED)}`}
          </Button>
        )}

        <p className="text-xs text-muted-foreground">
          Source: 10-K text mining
          {latestFiling ? ` | latest filing ${formatFilingDate(latestFiling)}` : ''}
          {totalExtracted > totalMatched
            ? ` | ${formatNumber(totalExtracted - totalMatched)} unmatched`
            : ''}
        </p>
      </div>
    </CollapsibleCard>
  )
}
