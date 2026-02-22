import { cn } from '@/lib/utils'

/**
 * Displays a data quality score with a small colored bar.
 * 80+ = green, 50-79 = yellow, <50 = gray.
 */
export function QualityIndicator({ score, className }) {
  if (score == null) {
    return <span className="text-muted-foreground">--</span>
  }

  const pct = Math.min(100, Math.max(0, score))
  const color =
    score >= 80 ? 'bg-green-500' :
    score >= 50 ? 'bg-yellow-500' :
    'bg-gray-400'

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <span className="text-sm font-medium tabular-nums w-7 text-right">{score}</span>
      <div className="h-2 w-16 bg-muted rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', color)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
