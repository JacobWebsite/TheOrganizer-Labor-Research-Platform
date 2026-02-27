import { useNavigate } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ChevronLeft, ChevronRight } from 'lucide-react'

const STATUS_STYLES = {
  pending: 'bg-yellow-100 text-yellow-800',
  running: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
}

function StatusBadge({ status, progress }) {
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium', STATUS_STYLES[status] || 'bg-gray-100 text-gray-800')}>
      {status}
      {status === 'running' && progress != null && (
        <span className="text-[10px]">{progress}%</span>
      )}
    </span>
  )
}

function formatDuration(seconds) {
  if (seconds == null) return '-'
  if (seconds < 60) return `${Math.round(seconds)}s`
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function ResearchRunsTable({ runs, total, page, pageSize, onPageChange }) {
  const navigate = useNavigate()
  const totalPages = Math.ceil(total / pageSize)

  return (
    <div>
      <div className="overflow-x-auto border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-3 py-2 text-left font-medium">Status</th>
              <th className="px-3 py-2 text-left font-medium">Company</th>
              <th className="px-3 py-2 text-left font-medium">Industry</th>
              <th className="px-3 py-2 text-right font-medium">Duration</th>
              <th className="px-3 py-2 text-right font-medium">Facts</th>
              <th className="px-3 py-2 text-right font-medium">Quality</th>
              <th className="px-3 py-2 text-right font-medium">Sections</th>
              <th className="px-3 py-2 text-left font-medium">Started</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr
                key={run.id}
                className="border-b cursor-pointer hover:bg-muted/30 transition-colors"
                onClick={() => navigate(`/research/${run.id}`)}
              >
                <td className="px-3 py-2">
                  <StatusBadge status={run.status} progress={run.progress_pct} />
                </td>
                <td className="px-3 py-2 font-medium">
                  <div>{run.company_name}</div>
                  {run.company_address && (
                    <div className="text-[10px] text-muted-foreground font-normal truncate max-w-[200px]" title={run.company_address}>
                      {run.company_address}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2 text-muted-foreground">{run.industry_naics || '-'}</td>
                <td className="px-3 py-2 text-right text-muted-foreground">{formatDuration(run.duration_seconds)}</td>
                <td className="px-3 py-2 text-right">{run.total_facts_found ?? '-'}</td>
                <td className={cn('px-3 py-2 text-right font-medium',
                  run.overall_quality_score != null
                    ? run.overall_quality_score >= 7 ? 'text-green-600' : run.overall_quality_score >= 5 ? 'text-yellow-600' : 'text-red-600'
                    : ''
                )}>
                  {run.overall_quality_score != null
                    ? Number(run.overall_quality_score).toFixed(1)
                    : '-'}
                </td>
                <td className="px-3 py-2 text-right">{run.sections_filled != null ? `${run.sections_filled}/7` : '-'}</td>
                <td className="px-3 py-2 text-muted-foreground">{formatDate(run.started_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-3">
          <p className="text-sm text-muted-foreground">
            Page {page} of {totalPages}
          </p>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
