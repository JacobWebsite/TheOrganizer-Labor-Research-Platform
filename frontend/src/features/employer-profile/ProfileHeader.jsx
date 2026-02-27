import { MapPin, Users, Building2, Landmark } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { SourceBadge } from '@/features/search/SourceBadge'
import { ConfidenceDots } from '@/shared/components/ConfidenceDots'
import { ProfileActionButtons } from './ProfileActionButtons'
import { cn } from '@/lib/utils'

const TIER_COLORS = {
  Priority: 'bg-red-600 text-white',
  Strong: 'bg-red-500 text-white',
  Promising: 'bg-red-400 text-stone-900',
  Moderate: 'bg-red-200 text-red-900',
  Low: 'bg-red-50 text-red-900',
}

function formatNumber(n) {
  if (n == null) return null
  return Number(n).toLocaleString()
}

export function ProfileHeader({ employer, scorecard, sourceType, isUnionReference, targetSignals }) {
  if (!employer) return null

  const name = employer.employer_name || employer.participant_name || employer.display_name || 'Unknown Employer'
  const city = employer.city || employer.unit_city
  const state = employer.state || employer.unit_state
  const location = [city, state].filter(Boolean).join(', ')
  const workers = employer.consolidated_workers || employer.unit_size || employer.total_workers || employer.employee_count
  const naicsCode = employer.naics_code || employer.naics_2digit || employer.naics
  const naicsDesc = employer.naics_description || employer.sector_name
  const unionName = employer.union_name
  const tier = scorecard?.score_tier
  const weightedScore = scorecard?.weighted_score
  const signalsPresent = targetSignals?.signals_present ?? null
  const hasEnforcement = targetSignals?.has_enforcement ?? false

  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl font-bold tracking-tight">{name}</h1>
              <SourceBadge source={sourceType || 'F7'} />
              {employer.match_confidence != null && (
                <ConfidenceDots confidence={employer.match_confidence} />
              )}
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

            {/* Union status label */}
            <div className="mt-1">
              {unionName ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium bg-green-50 text-green-700 border border-green-200">
                  <Landmark className="h-3.5 w-3.5" />
                  Represented by {unionName}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium bg-stone-50 text-stone-500 border border-stone-200">
                  No Known Union
                </span>
              )}
            </div>
          </div>

          {/* Non-union: signal count indicator */}
          {signalsPresent != null && !isUnionReference && (
            <div className="text-right shrink-0">
              <div className={cn('text-3xl font-bold', hasEnforcement ? 'text-red-600' : 'text-stone-600')}>
                {signalsPresent}/8
              </div>
              <div className="text-xs text-muted-foreground">Signals Detected</div>
            </div>
          )}

          {/* Union reference: label instead of score */}
          {isUnionReference && (
            <div className="text-right shrink-0">
              <span className="inline-flex items-center px-3 py-1.5 text-xs font-semibold bg-green-50 text-green-700 border border-green-200">
                Reference Data
              </span>
            </div>
          )}

          {/* Legacy: weighted score for F7 union employers without explicit flag */}
          {weightedScore != null && !isUnionReference && signalsPresent == null && (
            <div className="text-right shrink-0">
              <div className="text-3xl font-bold">{Number(weightedScore).toFixed(1)}</div>
              <div className="text-xs text-muted-foreground">Weighted Score</div>
            </div>
          )}
        </div>
        <ProfileActionButtons employer={employer} scorecard={scorecard} />
      </CardContent>
    </Card>
  )
}
