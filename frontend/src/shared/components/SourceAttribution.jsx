import { ConfidenceDots } from '@/shared/components/ConfidenceDots'
import { SOURCE_COLORS } from '@/shared/constants/sourceColors'

export function SourceAttribution({ attribution }) {
  if (!attribution) return null

  const colorClass = SOURCE_COLORS[attribution.source_system] || 'bg-muted text-muted-foreground border-border'

  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground mb-3 pb-2 border-b border-border/50">
      <span className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-semibold uppercase border shrink-0 ${colorClass}`}>
        {attribution.source_system}
      </span>
      <span className="truncate">
        {attribution.citation || attribution.source_label}
      </span>
      <ConfidenceDots
        confidence={attribution.best_confidence_score != null ? attribution.best_confidence_score : attribution.best_confidence}
        matchTier={attribution.best_match_tier}
        className="shrink-0"
      />
    </div>
  )
}
