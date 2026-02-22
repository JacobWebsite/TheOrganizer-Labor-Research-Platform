import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useTargetStats } from '@/shared/api/targets'

function StatItem({ label, value }) {
  return (
    <div>
      <p className="text-2xl font-bold tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  )
}

/**
 * Summary stats card for the targets page:
 * total non-union employers, quality distribution, top sources, flags.
 */
export function TargetStats() {
  const { data, isLoading } = useTargetStats()

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-4">
          <div className="flex gap-8">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="space-y-1">
                <Skeleton className="h-7 w-20" />
                <Skeleton className="h-4 w-24" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!data) return null

  const { total, flags, quality_distribution, by_source_origin, avg_source_count } = data

  // Calculate non-union count (total minus union)
  const nonUnionCount = total - (flags?.union_true || 0)

  // Top 3 source origins
  const topSources = (by_source_origin || []).slice(0, 3)

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex flex-wrap gap-x-10 gap-y-3">
          <StatItem label="Total employers" value={total?.toLocaleString() || '0'} />
          <StatItem label="Non-union" value={nonUnionCount.toLocaleString()} />
          <StatItem label="Federal contractors" value={(flags?.contractor_true || 0).toLocaleString()} />
          <StatItem label="Nonprofits" value={(flags?.nonprofit_true || 0).toLocaleString()} />
          <StatItem label="Avg sources/employer" value={avg_source_count || '0'} />
        </div>

        {/* Quality distribution + source origins */}
        <div className="mt-3 flex flex-wrap gap-x-8 gap-y-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <span className="font-medium text-foreground">Quality:</span>
            {(quality_distribution || []).map((d) => (
              <span key={d.tier}>{d.tier}: {Number(d.cnt).toLocaleString()}</span>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-foreground">Sources:</span>
            {topSources.map((s) => (
              <span key={s.source_origin}>{s.source_origin}: {Number(s.cnt).toLocaleString()}</span>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
