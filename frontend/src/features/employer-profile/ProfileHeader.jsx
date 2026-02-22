import { MapPin, Users, Building2, Landmark } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { SourceBadge } from '@/features/search/SourceBadge'
import { cn } from '@/lib/utils'

const TIER_COLORS = {
  Priority: 'bg-red-600 text-white',
  Strong: 'bg-orange-500 text-white',
  Promising: 'bg-yellow-500 text-black',
  Moderate: 'bg-stone-400 text-white',
  Low: 'bg-stone-200 text-stone-700',
}

function formatNumber(n) {
  if (n == null) return null
  return Number(n).toLocaleString()
}

export function ProfileHeader({ employer, scorecard, sourceType }) {
  if (!employer) return null

  const name = employer.employer_name || employer.participant_name || 'Unknown Employer'
  const city = employer.city || employer.unit_city
  const state = employer.state || employer.unit_state
  const location = [city, state].filter(Boolean).join(', ')
  const workers = employer.consolidated_workers || employer.unit_size || employer.total_workers
  const naicsCode = employer.naics_code || employer.naics_2digit
  const naicsDesc = employer.naics_description || employer.sector_name
  const unionName = employer.union_name
  const tier = scorecard?.score_tier
  const weightedScore = scorecard?.weighted_score

  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl font-bold tracking-tight">{name}</h1>
              <SourceBadge source={sourceType || 'F7'} />
              {tier && (
                <span className={cn('inline-flex items-center px-2 py-0.5 text-xs font-semibold', TIER_COLORS[tier] || 'bg-stone-200 text-stone-700')}>
                  {tier}
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
              {location && (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="h-3.5 w-3.5" />
                  {location}
                </span>
              )}
              {workers != null && (
                <span className="inline-flex items-center gap-1">
                  <Users className="h-3.5 w-3.5" />
                  {formatNumber(workers)} workers
                </span>
              )}
              {naicsCode && (
                <span className="inline-flex items-center gap-1">
                  <Building2 className="h-3.5 w-3.5" />
                  NAICS {naicsCode}{naicsDesc ? ` — ${naicsDesc}` : ''}
                </span>
              )}
              {unionName && (
                <span className="inline-flex items-center gap-1">
                  <Landmark className="h-3.5 w-3.5" />
                  {unionName}
                </span>
              )}
            </div>
          </div>

          {weightedScore != null && (
            <div className="text-right shrink-0">
              <div className="text-3xl font-bold">{Number(weightedScore).toFixed(1)}</div>
              <div className="text-xs text-muted-foreground">Weighted Score</div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
