import { useState } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from 'sonner'
import { useMatchReview, useReviewMatch } from '@/shared/api/admin'
import { ConfidenceDots } from '@/shared/components/ConfidenceDots'

const PAGE_SIZE = 20

export function MatchReviewCard() {
  const [filterSource, setFilterSource] = useState('')
  const [page, setPage] = useState(0)

  const { data, isLoading } = useMatchReview({
    source: filterSource || undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  })
  const reviewMutation = useReviewMatch()

  function handleAction(id, action) {
    reviewMutation.mutate(
      { id, action },
      {
        onSuccess: () => toast.success(`Match ${action}d successfully`),
        onError: (err) => toast.error(err.message || `Failed to ${action} match`),
      }
    )
  }

  const matches = data?.matches || []
  const total = data?.total || 0
  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between'>
        <CardTitle className='text-lg'>Match Review</CardTitle>
        <Select
          className='w-36'
          value={filterSource}
          onChange={(e) => {
            setFilterSource(e.target.value)
            setPage(0)
          }}
        >
          <option value=''>All Sources</option>
          <option value='osha'>OSHA</option>
          <option value='sam'>SAM</option>
          <option value='sec'>SEC</option>
          <option value='990'>990</option>
          <option value='whd'>WHD</option>
          <option value='bmf'>BMF</option>
          <option value='gleif'>GLEIF</option>
        </Select>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className='space-y-2'>
            <Skeleton className='h-8 w-full' />
            <Skeleton className='h-8 w-full' />
            <Skeleton className='h-8 w-full' />
          </div>
        ) : matches.length === 0 ? (
          <p className='py-4 text-center text-muted-foreground'>
            All clear &mdash; no reported issues.
          </p>
        ) : (
          <>
            <div className='overflow-x-auto'>
              <table className='w-full text-sm'>
                <thead>
                  <tr className='border-b text-left'>
                    <th className='pb-2 font-medium'>Employer</th>
                    <th className='pb-2 font-medium'>Matched Name</th>
                    <th className='pb-2 font-medium'>Source</th>
                    <th className='pb-2 font-medium text-right'>Score</th>
                    <th className='pb-2 font-medium text-right'>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {matches.map((match) => (
                    <tr key={match.id} className='border-b last:border-0'>
                      <td className='py-2'>{match.evidence?.target_name || match.target_id}</td>
                      <td className='py-2'>{match.evidence?.source_name || match.source_id}</td>
                      <td className='py-2 uppercase'>{match.source_system}</td>
                      <td className='py-2 text-right'>
                        <span className='inline-flex items-center gap-1.5'>
                          {match.confidence_score != null ? match.confidence_score.toFixed(2) : '\u2014'}
                          {match.confidence_score != null && (
                            <ConfidenceDots confidence={match.confidence_score} />
                          )}
                        </span>
                      </td>
                      <td className='py-2 text-right'>
                        <div className='flex justify-end gap-1'>
                          <Button
                            variant='outline'
                            size='sm'
                            onClick={() => handleAction(match.id, 'approve')}
                            disabled={reviewMutation.isPending}
                          >
                            Approve
                          </Button>
                          <Button
                            variant='destructive'
                            size='sm'
                            onClick={() => handleAction(match.id, 'reject')}
                            disabled={reviewMutation.isPending}
                          >
                            Reject
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className='mt-4 flex items-center justify-between'>
                <Button
                  variant='outline'
                  size='sm'
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  Previous
                </Button>
                <span className='text-sm text-muted-foreground'>
                  Page {page + 1} of {totalPages}
                </span>
                <Button
                  variant='outline'
                  size='sm'
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                >
                  Next
                </Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
