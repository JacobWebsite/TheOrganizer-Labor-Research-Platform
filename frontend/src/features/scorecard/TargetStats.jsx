import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useTargetStats } from '@/shared/api/targets'

function StatCard({ label, value, accent }) {
  return (
    <Card className={accent ? 'border-l-4 border-l-[#c23a22]' : ''}>
      <CardContent className="p-4">
        <p className="font-editorial text-2xl font-bold tabular-nums">{value}</p>
        <p className="text-xs uppercase tracking-wider text-muted-foreground mt-1">{label}</p>
      </CardContent>
    </Card>
  )
}

/**
 * Summary stats as 5 individual KPI cards for the targets page.
 */
export function TargetStats() {
  const { data, isLoading } = useTargetStats()

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {Array.from({ length: 5 }, (_, i) => (
          <Card key={i}>
            <CardContent className="p-4 space-y-2">
              <Skeleton className="h-7 w-20" />
              <Skeleton className="h-4 w-24" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  if (!data) return null

  const { total, flags, avg_source_count } = data

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
      <StatCard label="Total targets" value={total?.toLocaleString() || '0'} />
      <StatCard
        label="With enforcement"
        value={(flags?.enforcement_true || 0).toLocaleString()}
        accent
      />
      <StatCard label="Fed contractors" value={(flags?.contractor_true || 0).toLocaleString()} />
      <StatCard label="Nonprofits" value={(flags?.nonprofit_true || 0).toLocaleString()} />
      <StatCard label="Avg sources/emp" value={avg_source_count || '0'} />
    </div>
  )
}
