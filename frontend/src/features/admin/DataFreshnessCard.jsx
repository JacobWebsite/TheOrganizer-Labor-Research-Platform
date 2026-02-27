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
        <CardTitle>Data Freshness</CardTitle>
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
                <tr className='border-b bg-[#ede7db]'>
                  <th className='pb-2 pt-2 px-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground'>Source</th>
                  <th className='pb-2 pt-2 px-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground'>Rows</th>
                  <th className='pb-2 pt-2 px-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground'>Latest Date</th>
                  <th className='pb-2 pt-2 px-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground'>Status</th>
                </tr>
              </thead>
              <tbody>
                {(data?.sources || []).map((row, i) => (
                  <tr key={row.source_name} className={`border-b last:border-0 ${i % 2 === 1 ? 'bg-[#f5f0e8]/50' : ''}`}>
                    <td className='py-2 px-2 font-medium uppercase'>{row.source_name}</td>
                    <td className='py-2 px-2'>{formatNumber(row.row_count)}</td>
                    <td className='py-2 px-2'>{row.latest_record_date || row.last_refreshed?.split('T')[0] || '\u2014'}</td>
                    <td className='py-2 px-2'>
                      {row.stale ? (
                        <Badge className='bg-[#c23a22] text-white'>Stale</Badge>
                      ) : (
                        <Badge className='bg-[#3a7d44] text-white'>Fresh</Badge>
                      )}
                    </td>
                  </tr>
                ))}
                {(!data?.sources || data.sources.length === 0) && (
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
