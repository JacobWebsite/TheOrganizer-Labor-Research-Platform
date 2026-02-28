import { useNavigate, Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ChevronLeft, ChevronRight } from 'lucide-react'

const STATUS_STYLES = {
  pending: { bg: 'bg-[#8a7e6d]/10', text: 'text-[#8a7e6d]', dot: 'bg-[#8a7e6d]' },
  running: { bg: 'bg-[#c78c4e]/10', text: 'text-[#c78c4e]', dot: 'bg-[#c78c4e]' },
  completed: { bg: 'bg-[#3a7d44]/10', text: 'text-[#3a7d44]', dot: 'bg-[#3a7d44]' },
  failed: { bg: 'bg-[#c23a22]/10', text: 'text-[#c23a22]', dot: 'bg-[#c23a22]' },
}

function StatusBadge({ status, progress }) {
  const style = STATUS_STYLES[status] || { bg: 'bg-muted', text: 'text-muted-foreground', dot: 'bg-muted-foreground' }
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium', style.bg, style.text)}>
      <span className={cn('inline-block h-2 w-2 rounded-full', style.dot, status === 'running' && 'animate-pulse')} />
      {status}
      {status === 'running' && progress != null && (
        <span className="text-[10px]">{progress}%</span>
      )}
    </span>
  )
}

function qualityColor(score) {
  if (score == null) return ''
  if (score >= 7) return 'text-[#3a7d44]'
  if (score >= 5) return 'text-[#c78c4e]'
  return 'text-[#c23a22]'
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
      <div className="overflow-x-auto border rounded-lg">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-[#ede7db]">
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Status</th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Company</th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Industry</th>
              <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">Duration</th>
              <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">Facts</th>
              <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">Quality</th>
              <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">Sections</th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Started</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run, i) => (
              <tr
                key={run.id}
                className={cn(
                  'border-b cursor-pointer hover:bg-accent/50 transition-colors',
                  i % 2 === 1 && 'bg-[#f5f0e8]/50'
                )}
                onClick={() => navigate(`/research/${run.id}`)}
              >
                <td className="px-3 py-2">
                  <StatusBadge status={run.status} progress={run.progress_pct} />
                </td>
                <td className="px-3 py-2 font-medium">
                  <div>
                    {run.employer_id ? (
                      <Link
                        to={`/employers/${run.employer_id}`}
                        className="text-[#1a6b5a] hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {run.company_name}
                      </Link>
                    ) : run.company_name}
                  </div>
                  {run.company_address && (
                    <div className="text-[10px] text-muted-foreground font-normal truncate max-w-[200px]" title={run.company_address}>
                      {run.company_address}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2 text-muted-foreground">{run.industry_naics || '-'}</td>
                <td className="px-3 py-2 text-right text-muted-foreground">{formatDuration(run.duration_seconds)}</td>
                <td className="px-3 py-2 text-right">{run.total_facts_found ?? '-'}</td>
                <td className={cn('px-3 py-2 text-right font-medium', qualityColor(run.overall_quality_score))}>
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
