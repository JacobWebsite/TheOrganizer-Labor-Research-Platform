import { useState, useEffect } from 'react'
import { RefreshCw, ThumbsUp, ThumbsDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const STATUS_COLORS = {
  pending: 'bg-[#c78c4e]',
  running: 'bg-[#3a6b8c]',
  completed: 'bg-[#3a7d44]',
  failed: 'bg-[#c23a22]',
}

function formatDuration(seconds) {
  if (seconds == null) return '-'
  if (seconds < 60) return `${Math.round(seconds)}s`
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

function LiveTimer({ startedAt }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const start = new Date(startedAt).getTime()
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [startedAt])
  return <span>{formatDuration(elapsed)}</span>
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

function qualityColor(score) {
  if (score == null) return ''
  if (score >= 7) return 'text-[#3a7d44]'
  if (score >= 5) return 'text-[#c78c4e]'
  return 'text-[#c23a22]'
}

export function DossierHeader({ status, onRunAgain, onUsefulnessChange }) {
  const isInProgress = status?.status === 'pending' || status?.status === 'running'

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h1 className="font-editorial text-2xl font-bold">{status?.company_name || 'Research Run'}</h1>
            {status?.company_address && (
              <p className="text-sm text-muted-foreground">{status.company_address}</p>
            )}
            <div className="flex items-center gap-2 mt-1">
              <span className={cn(
                'inline-block h-2 w-2 rounded-full',
                STATUS_COLORS[status?.status] || 'bg-[#d9cebb]'
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

        {/* Metadata grid — always visible, shows live stats during running */}
        <div className="grid grid-cols-2 gap-4 mt-3 sm:grid-cols-5">
          <div>
            <p className="text-xs text-muted-foreground">Duration</p>
            <p className="text-sm font-medium">
              {isInProgress && status?.started_at
                ? <LiveTimer startedAt={status.started_at} />
                : formatDuration(status?.duration_seconds)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Facts Found</p>
            <p className="text-sm font-medium">{status?.total_facts_found ?? (isInProgress ? '...' : '-')}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Sections</p>
            <p className="text-sm font-medium">{status?.sections_filled != null ? `${status.sections_filled}/10` : (isInProgress ? '...' : '-')}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Tools Called</p>
            <p className="text-sm font-medium">{status?.total_tools_called ?? (isInProgress ? '...' : '-')}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Quality</p>
            <p className={cn('text-sm font-medium', qualityColor(status?.overall_quality_score))}>
              {status?.overall_quality_score != null ? `${Number(status.overall_quality_score).toFixed(1)}/10` : (isInProgress ? '...' : '-')}
            </p>
          </div>
        </div>

        {/* Run-level quick review (Feature 1) */}
        {status?.status === 'completed' && onUsefulnessChange && (
          <div className="flex items-center gap-3 mt-3 pt-3 border-t border-muted">
            <span className="text-xs text-muted-foreground">Was this research useful?</span>
            <button
              onClick={() => onUsefulnessChange(true)}
              className={cn(
                'inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors',
                status?.run_usefulness === true
                  ? 'bg-[#3a7d44]/15 text-[#3a7d44] border border-[#3a7d44]/30'
                  : 'text-[#8a7e6d] hover:bg-[#3a7d44]/10 hover:text-[#3a7d44] border border-transparent'
              )}
              title="Useful"
            >
              <ThumbsUp className="h-3.5 w-3.5" />
              Useful
            </button>
            <button
              onClick={() => onUsefulnessChange(false)}
              className={cn(
                'inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors',
                status?.run_usefulness === false
                  ? 'bg-[#c23a22]/15 text-[#c23a22] border border-[#c23a22]/30'
                  : 'text-[#8a7e6d] hover:bg-[#c23a22]/10 hover:text-[#c23a22] border border-transparent'
              )}
              title="Not Useful"
            >
              <ThumbsDown className="h-3.5 w-3.5" />
              Not Useful
            </button>
            {status?.run_usefulness != null && (
              <span className="text-[10px] text-muted-foreground ml-auto">Saved</span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
