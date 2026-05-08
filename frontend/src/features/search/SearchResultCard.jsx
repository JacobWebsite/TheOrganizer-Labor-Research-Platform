import { useNavigate } from 'react-router-dom'
import { MapPin, Users, AlertTriangle } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { SourceBadge } from './SourceBadge'

function formatNumber(n) {
  if (n == null) return null
  return Number(n).toLocaleString()
}

const TIER_BORDER = {
  Priority: 'border-l-[#c23a22]',
  Strong: 'border-l-[#1a6b5a]',
  Promising: 'border-l-[#c78c4e]',
}

export function SearchResultCard({ employer }) {
  const navigate = useNavigate()
  const workers = employer.consolidated_workers || employer.unit_size
  const location = [employer.city, employer.state].filter(Boolean).join(', ')
  const tierBorder = TIER_BORDER[employer.score_tier] || 'border-l-transparent'

  return (
    <Card
      className={`cursor-pointer hover:bg-accent/50 transition-colors border-l-4 ${tierBorder}`}
      onClick={() => navigate(`/employers/${employer.canonical_id}`)}
    >
      <CardContent className="p-4 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="font-medium leading-tight">
            {employer.employer_name}
            {employer.group_member_count > 1 && (
              <span className="ml-1.5 text-xs text-muted-foreground">
                ({employer.group_member_count} locations)
              </span>
            )}
          </div>
          <SourceBadge source={employer.source_type} />
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {location && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" /> {location}
            </span>
          )}
          {workers != null && (
            <span className="inline-flex items-center gap-1">
              <Users className="h-3 w-3" /> {formatNumber(workers)} workers
            </span>
          )}
          {employer.source_type === 'F7' && employer.direct_factors_available != null && (() => {
            const d = employer.direct_factors_available
            const cls = d >= 3
              ? 'bg-[#1a6b5a]/20 text-[#1a6b5a]'
              : d >= 1
                ? 'bg-[#c78c4e]/20 text-[#c78c4e]'
                : 'bg-amber-100 text-amber-800 border border-amber-300'
            return (
              <span
                className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium ${cls}`}
                title="Direct employer-specific records (OSHA, NLRB, WHD, contracts, financial)"
              >
                {d}/5 direct
              </span>
            )
          })()}
          {employer.has_thin_data && (
            <span
              className="inline-flex items-center gap-0.5 rounded-md bg-amber-100 text-amber-800 border border-amber-300 px-1.5 py-0.5 text-[10px] font-medium"
              title="High score comes from modeled signals (similarity, size, industry), not employer-specific records"
            >
              <AlertTriangle className="h-2.5 w-2.5" />
              thin data
            </span>
          )}
        </div>
        {employer.union_name && (
          <div className="text-xs text-muted-foreground truncate">
            Union: {employer.union_name}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
