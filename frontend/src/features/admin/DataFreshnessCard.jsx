import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Loader2, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { useDataFreshness, useRefreshFreshness } from '@/shared/api/admin'

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

export function DataFreshnessCard() {
  const { data, isLoading } = useDataFreshness()
  const refreshMutation = useRefreshFreshness()

  function handleRefresh() {
    refreshMutation.mutate(undefined, {
      onSuccess: () => toast.success('Data freshness refreshed'),
      onError: (err) => toast.error(err.message || 'Failed to refresh freshness'),
    })
  }

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between'>
        <CardTitle className='text-lg'>Data Freshness</CardTitle>
        <Button
          variant='outline'
          size='sm'
          onClick={handleRefresh}
          disabled={refreshMutation.isPending}
        >
          {refreshMutation.isPending ? (
            <Loader2 className='h-4 w-4 animate-spin' />
          ) : (
            <RefreshCw className='h-4 w-4' />
          )}
          <span className='ml-1'>Refresh</span>
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className='space-y-2'>
            <Skeleton className='h-8 w-full' />
            <Skeleton className='h-8 w-full' />
            <Skeleton className='h-8 w-full' />
          </div>
        ) : (
          <div className='overflow-x-auto'>
            <table className='w-full text-sm'>
              <thead>
                <tr className='border-b text-left'>
                  <th className='pb-2 font-medium'>Source</th>
                  <th className='pb-2 font-medium'>Rows</th>
                  <th className='pb-2 font-medium'>Latest Date</th>
                  <th className='pb-2 font-medium'>Status</th>
                </tr>
              </thead>
              <tbody>
                {Array.isArray(data) && data.map((row) => (
                  <tr key={row.source} className='border-b last:border-0'>
                    <td className='py-2 font-medium uppercase'>{row.source}</td>
                    <td className='py-2'>{formatNumber(row.row_count)}</td>
                    <td className='py-2'>{row.latest_date || '\u2014'}</td>
                    <td className='py-2'>
                      {row.is_stale ? (
                        <Badge variant='destructive'>Stale</Badge>
                      ) : (
                        <Badge className='bg-green-600 text-white'>Fresh</Badge>
                      )}
                    </td>
                  </tr>
                ))}
                {(!Array.isArray(data) || data.length === 0) && (
                  <tr>
                    <td colSpan={4} className='py-4 text-center text-muted-foreground'>
                      No freshness data available
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
