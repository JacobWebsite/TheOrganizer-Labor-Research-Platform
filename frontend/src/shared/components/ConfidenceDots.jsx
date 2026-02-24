import { cn } from '@/lib/utils'

const TIER_MAP = {
  // Phase 2 canonical tier names
  EIN_EXACT: 4,
  NAME_CITY_STATE_EXACT: 3,
  NAME_STATE_EXACT: 3,
  NAME_AGGRESSIVE_STATE: 2,
  FUZZY_SPLINK_ADAPTIVE: 2,
  FUZZY_TRIGRAM: 1,
  // Legacy tier names (backward compat)
  EIN_MATCH: 4,
  NAME_CITY_STATE: 3,
  NAME_STATE: 3,
  AGGRESSIVE_FUZZY: 2,
  SPLINK: 2,
  TRIGRAM: 1,
}

export function ConfidenceDots({ confidence, matchTier, className }) {
  // Determine dot count from confidence score or match tier
  let dots = 2 // default medium
  if (matchTier && TIER_MAP[matchTier]) {
    dots = TIER_MAP[matchTier]
  } else if (confidence != null) {
    if (confidence >= 0.9) dots = 4
    else if (confidence >= 0.7) dots = 3
    else if (confidence >= 0.5) dots = 2
    else dots = 1
  }

  return (
    <span className={cn('inline-flex gap-0.5', className)} title={`Match confidence: ${dots}/4`}>
      {[1, 2, 3, 4].map((i) => (
        <span
          key={i}
          className={cn(
            'inline-block h-2 w-2 rounded-full',
            i <= dots ? 'bg-foreground' : 'bg-muted-foreground/30'
          )}
        />
      ))}
    </span>
  )
}
