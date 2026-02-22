import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { usePlatformStats } from '@/shared/api/admin'

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

function StatItem({ label, value }) {
  return (
    <div className='space-y-1'>
      <p className='text-sm text-muted-foreground'>{label}</p>
      <p className='text-2xl font-bold'>{formatNumber(value)}</p>
    </div>
  )
}

export function PlatformStatsCard() {
  const { data, isLoading } = usePlatformStats()

  const avgMatches =
    data?.total_employers && data?.total_matches
      ? (data.total_matches / data.total_employers).toFixed(1)
      : null

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-lg'>Platform Statistics</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className='grid grid-cols-2 gap-4'>
            <Skeleton className='h-14 w-full' />
            <Skeleton className='h-14 w-full' />
            <Skeleton className='h-14 w-full' />
            <Skeleton className='h-14 w-full' />
          </div>
        ) : (
          <div className='grid grid-cols-2 gap-4'>
            <StatItem label='Total Employers' value={data?.total_employers} />
            <StatItem label='Scorecard Rows' value={data?.total_scorecard} />
            <StatItem label='Total Matches' value={data?.total_matches} />
            <StatItem label='Avg Matches/Employer' value={avgMatches} />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
