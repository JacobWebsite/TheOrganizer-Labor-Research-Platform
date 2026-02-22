import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Loader2, RefreshCw, Database } from 'lucide-react'
import { toast } from 'sonner'
import { useRefreshScorecard, useRefreshFreshness } from '@/shared/api/admin'

export function RefreshActionsCard() {
  const scorecardMutation = useRefreshScorecard()
  const freshnessMutation = useRefreshFreshness()

  function handleRefreshScorecard() {
    scorecardMutation.mutate(undefined, {
      onSuccess: () => toast.success('Scorecard refreshed'),
      onError: (err) => toast.error(err.message || 'Failed to refresh scorecard'),
    })
  }

  function handleRefreshFreshness() {
    freshnessMutation.mutate(undefined, {
      onSuccess: () => toast.success('Data freshness refreshed'),
      onError: (err) => toast.error(err.message || 'Failed to refresh freshness'),
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-lg'>Maintenance Actions</CardTitle>
      </CardHeader>
      <CardContent>
        <div className='space-y-3'>
          <Button
            variant='outline'
            className='w-full justify-start'
            onClick={handleRefreshScorecard}
            disabled={scorecardMutation.isPending}
          >
            {scorecardMutation.isPending ? (
              <Loader2 className='mr-2 h-4 w-4 animate-spin' />
            ) : (
              <RefreshCw className='mr-2 h-4 w-4' />
            )}
            Refresh Scorecard
          </Button>
          <Button
            variant='outline'
            className='w-full justify-start'
            onClick={handleRefreshFreshness}
            disabled={freshnessMutation.isPending}
          >
            {freshnessMutation.isPending ? (
              <Loader2 className='mr-2 h-4 w-4 animate-spin' />
            ) : (
              <Database className='mr-2 h-4 w-4' />
            )}
            Refresh Freshness
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
