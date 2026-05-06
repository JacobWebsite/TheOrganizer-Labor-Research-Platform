import { MapPin, Users, Building2, Landmark } from 'lucide-react'
import { SourceBadge } from '@/features/search/SourceBadge'
import { ConfidenceDots } from '@/shared/components/ConfidenceDots'
import { cn } from '@/lib/utils'
import { EntityContextBlock } from './EntityContextBlock'

const TIER_COLORS = {
  Priority: 'border border-[#c78c4e] text-[#c78c4e]',
  Strong: 'border border-[#1a6b5a] text-[#1a6b5a]',
  Promising: 'border border-[#c78c4e]/60 text-[#c78c4e]',
  Moderate: 'border border-[#faf6ef]/30 text-[#faf6ef]/60',
  Low: 'border border-[#faf6ef]/20 text-[#faf6ef]/40',
  // Speculative (2026-05-06): muted gray-blue + dashed border to
  // visually distinguish from Low (which has real enforcement) and
  // signal "modeled, unverified."
  Speculative: 'border border-dashed border-[#7a8b9a]/60 text-[#7a8b9a]',
}

const DATA_SOURCE_KEYS = [
  { key: 'has_osha', label: 'OSHA' },
  { key: 'has_nlrb', label: 'NLRB' },
  { key: 'has_whd', label: 'WHD' },
  { key: 'has_sam', label: 'SAM' },
  { key: 'has_sec', label: 'SEC' },
  { key: 'has_990', label: '990' },
  { key: 'has_mergent', label: 'GLEIF' },
  { key: 'has_form5500', label: 'F5500' },
]

function formatNumber(n) {
  if (n == null) return null
  return Number(n).toLocaleString()
}

export function ProfileHeader({ employer, scorecard, sourceType, isUnionReference, targetSignals, summaryParts, dataSources, entityContext }) {
  if (!employer) return null

  const name = employer.employer_name || employer.participant_name || employer.display_name || 'Unknown Employer'
  const city = employer.city || employer.unit_city
  const state = employer.state || employer.unit_state
  const location = [city, state].filter(Boolean).join(', ')
  // Legacy fallback when entityContext is unavailable (older API responses).
  const workers = employer.consolidated_workers || employer.unit_size || employer.total_workers || employer.employee_count
  const naicsCode = employer.naics_code || employer.naics_2digit || employer.naics
  const naicsDesc = employer.naics_description || employer.sector_name
  const unionName = employer.union_name || employer.latest_union_name
  const tier = scorecard?.score_tier
  const weightedScore = scorecard?.weighted_score
  const signalsPresent = targetSignals?.signals_present ?? null
  const hasEnforcement = targetSignals?.has_enforcement ?? false

  // Collect source badges from dataSources
  const activeSources = dataSources
    ? DATA_SOURCE_KEYS.filter(s => dataSources[s.key]).map(s => s.label)
    : []

  return (
    <div className="rounded-lg p-6 sm:p-8" style={{ background: 'linear-gradient(135deg, #2c2418 0%, #3d3225 100%)' }}>
      <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
        {/* Left side */}
        <div className="space-y-3 min-w-0 flex-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="font-editorial text-[30px] font-bold text-[#faf6ef] leading-tight">{name}</h1>
            {tier && (
              <span className={cn('inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold', TIER_COLORS[tier] || 'border border-[#faf6ef]/30 text-[#faf6ef]/60')}>
                {tier}
              </span>
            )}
            {employer.match_confidence != null && (
              <ConfidenceDots confidence={employer.match_confidence} />
            )}
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-[#faf6ef]/70">
            {location && (
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3.5 w-3.5" />
                {location}
              </span>
            )}
            {naicsCode && (
              <span className="inline-flex items-center gap-1">
                <Building2 className="h-3.5 w-3.5" />
                NAICS {naicsCode}{naicsDesc ? ` -- ${naicsDesc}` : ''}
              </span>
            )}
            <EntityContextBlock
              entityContext={entityContext}
              legacyWorkers={workers}
              sizeSource={scorecard?.size_source}
            />
            {unionName && (
              <span className="inline-flex items-center gap-1">
                <Landmark className="h-3.5 w-3.5" />
                {unionName}
              </span>
            )}
          </div>

          {/* Union status label */}
          <div>
            {unionName ? (
              <span className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium bg-[#3a7d44]/20 text-[#3a7d44] border border-[#3a7d44]/30">
                <Landmark className="h-3.5 w-3.5" />
                Represented by {unionName}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium bg-[#faf6ef]/10 text-[#faf6ef]/60 border border-[#faf6ef]/20">
                No Known Union
              </span>
            )}
          </div>

          {/* Summary box */}
          {summaryParts && summaryParts.length > 0 && (
            <div className="border-l-4 border-l-[#c23a22] rounded-r px-4 py-2.5 mt-1" style={{ background: 'rgba(250,246,239,0.08)' }}>
              <p className="text-sm text-[#faf6ef]/80">
                {summaryParts.join(' \u00b7 ')}
              </p>
            </div>
          )}
        </div>

        {/* Right side — score */}
        <div className="text-right shrink-0">
          {/* Non-union: signal count indicator */}
          {signalsPresent != null && !isUnionReference && (
            <>
              <div className={cn('text-[48px] font-editorial font-bold leading-none', hasEnforcement ? 'text-[#c23a22]' : 'text-[#faf6ef]')}>
                {signalsPresent}/9
              </div>
              <div className="text-[10px] uppercase tracking-widest text-[#faf6ef]/50 mt-1">Signals Detected</div>
            </>
          )}

          {/* Union reference: label + factors badge */}
          {isUnionReference && (
            <div className="flex flex-col items-end gap-2">
              <span className="inline-flex items-center rounded-md px-3 py-1.5 text-xs font-semibold bg-[#3a7d44]/20 text-[#3a7d44] border border-[#3a7d44]/30">
                Reference Data
              </span>
              {scorecard?.factors_available != null && (() => {
                const factors = scorecard.factors_available
                const total = scorecard.factors_total || 10
                return (
                  <span className={cn(
                    'rounded-md px-2 py-0.5 text-xs font-medium',
                    factors >= 5 ? 'bg-[#1a6b5a]/20 text-[#1a6b5a]' :
                    factors >= 3 ? 'bg-[#c78c4e]/20 text-[#c78c4e]' :
                    'bg-amber-100 text-amber-800 border border-amber-300'
                  )}>
                    {factors}/{total} factors
                  </span>
                )
              })()}
            </div>
          )}

          {/* Legacy: weighted score for F7 union employers without explicit flag */}
          {weightedScore != null && !isUnionReference && signalsPresent == null && (
            <>
              <div className="text-[48px] font-editorial font-bold text-[#faf6ef] leading-none">
                {Number(weightedScore).toFixed(1)}
              </div>
              <div className="text-[10px] uppercase tracking-widest text-[#faf6ef]/50 mt-1">Composite Score</div>
              {scorecard?.factors_available != null && (() => {
                const factors = scorecard.factors_available
                const total = scorecard.factors_total || 10
                return (
                  <span className={cn(
                    'rounded-md px-2 py-0.5 text-xs font-medium mt-2 inline-block',
                    factors >= 5 ? 'bg-[#1a6b5a]/20 text-[#1a6b5a]' :
                    factors >= 3 ? 'bg-[#c78c4e]/20 text-[#c78c4e]' :
                    'bg-amber-100 text-amber-800 border border-amber-300'
                  )}>
                    {factors}/{total} factors
                  </span>
                )
              })()}
            </>
          )}
        </div>
      </div>

      {/* Bottom: source badges row */}
      {(activeSources.length > 0 || sourceType) && (
        <div className="flex items-center gap-2 mt-5 pt-4 border-t border-[#faf6ef]/10 flex-wrap">
          <SourceBadge source={sourceType || 'F7'} />
          {activeSources.map(src => (
            <SourceBadge key={src} source={src} />
          ))}
        </div>
      )}
    </div>
  )
}
