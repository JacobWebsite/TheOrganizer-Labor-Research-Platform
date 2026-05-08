import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Users, Building2, Vote, Briefcase, ShieldCheck } from 'lucide-react'
import { useUnionOverview, useNationalUnions } from '@/shared/api/unions'

/**
 * Format large numbers with abbreviations (e.g. 14507549 -> "14.5M").
 */
function formatCompact(n) {
  if (n == null) return '\u2014'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toLocaleString()
}

/**
 * Overview card with key union metrics + clickable affiliation chips.
 */
export function NationalUnionsSummary({ onAffiliationClick }) {
  const { data: overview, isLoading: overviewLoading } = useUnionOverview()
  const { data: nationalData, isLoading: nationalLoading } = useNationalUnions()

  const isLoading = overviewLoading || nationalLoading
  const affiliations = nationalData?.national_unions || []

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <Skeleton className="h-6 w-48" />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
            {Array.from({ length: 5 }, (_, i) => (
              <div key={i} className="space-y-1">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-7 w-24" />
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-6 w-20" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!overview) return null

  const winPct = overview.recent_elections > 0
    ? ((overview.recent_wins / overview.recent_elections) * 100).toFixed(1)
    : null

  const metrics = [
    {
      label: 'Total Members',
      value: formatCompact(overview.total_members),
      icon: Users,
      color: '#1a6b5a',
    },
    {
      label: 'Active Unions',
      value: overview.active_unions?.toLocaleString() ?? '\u2014',
      icon: ShieldCheck,
      color: '#2c2418',
    },
    {
      label: 'Covered Employers',
      value: overview.total_employers?.toLocaleString() ?? '\u2014',
      icon: Building2,
      color: '#3a6b8c',
    },
    {
      label: 'Covered Workers',
      value: formatCompact(overview.total_covered_workers),
      icon: Briefcase,
      color: '#c78c4e',
    },
    {
      label: 'Recent Elections',
      value: winPct
        ? `${overview.recent_wins.toLocaleString()} of ${overview.recent_elections.toLocaleString()} won (${winPct}%)`
        : '\u2014',
      sublabel: 'Last 12 months',
      icon: Vote,
      color: '#3a7d44',
    },
  ]

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle>Union Landscape</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Metrics row */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
          {metrics.map(({ label, value, sublabel, icon: Icon, color }) => (
            <div key={label} className="space-y-0.5">
              <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-[#8a7e6b]">
                <Icon className="h-3.5 w-3.5" style={{ color }} />
                {label}
              </div>
              <p className="text-lg font-bold tabular-nums text-[#2c2418]">{value}</p>
              {sublabel && (
                <p className="text-[10px] text-[#8a7e6b]">{sublabel}</p>
              )}
            </div>
          ))}
        </div>

        {/* Affiliation chips */}
        {affiliations.length > 0 && (
          <div className="border-t border-[#d9cebb] pt-3">
            <p className="text-xs font-medium uppercase tracking-wider text-[#8a7e6b] mb-2">
              Affiliations
            </p>
            <div className="flex flex-wrap gap-2">
              {affiliations.map((a) => (
                <button
                  key={a.aff_abbr}
                  type="button"
                  onClick={() => onAffiliationClick(a.aff_abbr)}
                  className="cursor-pointer"
                >
                  <Badge variant="secondary" className="hover:bg-primary hover:text-primary-foreground transition-colors">
                    {a.aff_abbr}
                    <span className="ml-1 text-[10px] opacity-70">
                      {formatCompact(a.deduplicated_members ?? a.total_members ?? 0)}
                    </span>
                  </Badge>
                </button>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
