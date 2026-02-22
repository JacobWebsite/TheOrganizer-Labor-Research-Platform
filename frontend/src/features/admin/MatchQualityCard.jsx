import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useMatchQuality } from '@/shared/api/admin'

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

const CONFIDENCE_COLORS = {
  HIGH: 'bg-green-600 text-white',
  MEDIUM: 'bg-yellow-500 text-black',
  LOW: 'bg-gray-400 text-white',
}

export function MatchQualityCard() {
  const { data, isLoading } = useMatchQuality()

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-lg'>Match Quality</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className='space-y-2'>
            <Skeleton className='h-8 w-48' />
            <Skeleton className='h-8 w-full' />
            <Skeleton className='h-8 w-full' />
          </div>
        ) : (
          <div className='space-y-6'>
            <div>
              <p className='text-sm text-muted-foreground'>Total Matches</p>
              <p className='text-2xl font-bold'>{formatNumber(data?.total_matches)}</p>
            </div>

            {data?.by_source && data.by_source.length > 0 && (
              <div>
                <h4 className='mb-2 text-sm font-medium'>By Source</h4>
                <table className='w-full text-sm'>
                  <thead>
                    <tr className='border-b text-left'>
                      <th className='pb-2 font-medium'>Source</th>
                      <th className='pb-2 font-medium text-right'>Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_source.map((row) => (
                      <tr key={row.source} className='border-b last:border-0'>
                        <td className='py-2 uppercase'>{row.source}</td>
                        <td className='py-2 text-right'>{formatNumber(row.count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {data?.by_confidence && data.by_confidence.length > 0 && (
              <div>
                <h4 className='mb-2 text-sm font-medium'>By Confidence</h4>
                <div className='flex flex-wrap gap-2'>
                  {data.by_confidence.map((row) => (
                    <Badge
                      key={row.confidence}
                      className={CONFIDENCE_COLORS[row.confidence] || ''}
                    >
                      {row.confidence}: {formatNumber(row.count)}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
