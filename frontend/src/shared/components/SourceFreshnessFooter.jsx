import { useDataFreshness } from '@/shared/api/admin'

/**
 * Source-level freshness footer for profile cards.
 *
 * Shows "{Display Name}: data refreshed through {date}" when the per-employer
 * latest_record_date is unavailable. Cards should pass `latestRecordDate` as
 * the per-employer date; this component renders the source-level fallback
 * when that is null.
 *
 * Background: P1 #28 ("Data current through" labels). The OSHA/NLRB/WHD cards
 * already render their own "X data current through {date}" line when an
 * employer has records. This component covers the empty case so users always
 * see freshness context, not silence.
 */
export function SourceFreshnessFooter({ sourceName, latestRecordDate }) {
  const { data, isLoading } = useDataFreshness()

  // Per-employer date wins -- the parent card already renders that line,
  // so we render nothing to avoid duplicating.
  if (latestRecordDate) return null
  if (isLoading || !data?.sources) return null

  const row = data.sources.find((s) => s.source_name === sourceName)
  if (!row) return null

  const date = row.latest_record_date
  if (!date) return null

  let formatted = date
  try {
    const parsed = new Date(date)
    if (!Number.isNaN(parsed.getTime())) {
      formatted = parsed.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    }
  } catch {
    // fall through with raw date string
  }

  const staleSuffix = row.stale ? ' (over 6 months old)' : ''

  return (
    <p className="text-xs text-muted-foreground">
      {row.display_name || sourceName}: data refreshed through {formatted}
      {staleSuffix}
    </p>
  )
}
