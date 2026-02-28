import { Link2 } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { ConfidenceDots } from '@/shared/components/ConfidenceDots'
import { SOURCE_COLORS } from '@/shared/constants/sourceColors'

export function DataProvenanceCard({ matchSummary }) {
  if (!matchSummary || matchSummary.length === 0) return null

  const summary = `${matchSummary.length} source${matchSummary.length === 1 ? '' : 's'} linked`

  return (
    <CollapsibleCard icon={Link2} title="Data Provenance" summary={summary}>
      <div className="space-y-3">
        {matchSummary.map((entry) => {
          const colorClass = SOURCE_COLORS[entry.source_system] || 'bg-muted text-muted-foreground border-border'
          return (
            <div key={entry.source_system} className="flex items-start gap-3 text-sm">
              <span className={`inline-flex items-center px-2 py-0.5 text-xs font-semibold uppercase border shrink-0 ${colorClass}`}>
                {entry.source_system}
              </span>
              <div className="flex-1 min-w-0">
                <div className="font-medium">{entry.source_label}</div>
                <div className="text-muted-foreground text-xs mt-0.5">{entry.citation}</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {entry.match_count > 1 && (
                  <span className="text-xs text-muted-foreground">{entry.match_count} records</span>
                )}
                <ConfidenceDots
                  confidence={entry.best_confidence_score != null ? entry.best_confidence_score : entry.best_confidence}
                  matchTier={entry.best_match_tier}
                />
              </div>
            </div>
          )
        })}
      </div>
    </CollapsibleCard>
  )
}
