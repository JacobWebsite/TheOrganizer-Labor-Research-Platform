import { RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const STATUS_COLORS = {
  pending: 'bg-yellow-500',
  running: 'bg-blue-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
}

function formatDuration(seconds) {
  if (seconds == null) return '-'
  if (seconds < 60) return `${Math.round(seconds)}s`
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

function ProgressBar({ progress, status }) {
  if (status !== 'running' && status !== 'pending') return null

  return (
    <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
      <div
        className={cn('h-full rounded-full transition-all duration-500', STATUS_COLORS[status])}
        style={{ width: `${Math.max(progress || 0, 2)}%` }}
      />
    </div>
  )
}

export function DossierHeader({ status, onRunAgain }) {
  const isInProgress = status?.status === 'pending' || status?.status === 'running'

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h1 className="text-2xl font-bold">{status?.company_name || 'Research Run'}</h1>
            {status?.company_address && (
              <p className="text-sm text-muted-foreground">{status.company_address}</p>
            )}
            <div className="flex items-center gap-2 mt-1">
              <span className={cn(
                'inline-block h-2 w-2 rounded-full',
                STATUS_COLORS[status?.status] || 'bg-gray-400'
              )} />
              <span className="text-sm text-muted-foreground capitalize">{status?.status || 'unknown'}</span>
            </div>
          </div>
          {!isInProgress && onRunAgain && (
            <Button variant="outline" size="sm" className="gap-1.5" onClick={onRunAgain}>
              <RefreshCw className="h-3.5 w-3.5" />
              Run Again
            </Button>
          )}
        </div>

        <ProgressBar progress={status?.progress_pct} status={status?.status} />

        {isInProgress && status?.current_step && (
          <p className="text-sm text-muted-foreground mt-2 animate-pulse">
            {status.current_step}
          </p>
        )}

        {!isInProgress && (
          <div className="grid grid-cols-2 gap-4 mt-3 sm:grid-cols-5">
            <div>
              <p className="text-xs text-muted-foreground">Duration</p>
              <p className="text-sm font-medium">{formatDuration(status?.duration_seconds)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Facts Found</p>
              <p className="text-sm font-medium">{status?.total_facts_found ?? '-'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Sections</p>
              <p className="text-sm font-medium">{status?.sections_filled != null ? `${status.sections_filled}/7` : '-'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Tools Called</p>
              <p className="text-sm font-medium">{status?.total_tools_called ?? '-'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Quality</p>
              <p className={cn('text-sm font-medium', status?.overall_quality_score != null
                ? status.overall_quality_score >= 7 ? 'text-green-600' : status.overall_quality_score >= 5 ? 'text-yellow-600' : 'text-red-600'
                : ''
              )}>
                {status?.overall_quality_score != null ? `${Number(status.overall_quality_score).toFixed(1)}/10` : '-'}
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
