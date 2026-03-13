import { useState } from 'react'
import { Terminal, CheckCircle2, XCircle, AlertTriangle, ChevronRight } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { cn } from '@/lib/utils'

export function ActionLog({ actions }) {
  if (!actions || actions.length === 0) return null

  const found = actions.filter(a => a.data_found && !a.error_message)
  const errored = actions.filter(a => a.error_message)
  const notFound = actions.filter(a => !a.data_found && !a.error_message)

  const totalTime = actions.reduce((sum, a) => sum + (a.latency_ms || 0), 0)
  const summaryText = `${actions.length} tools called -- ${found.length} found data${errored.length ? `, ${errored.length} error${errored.length !== 1 ? 's' : ''}` : ''}`

  return (
    <CollapsibleCard
      icon={Terminal}
      title="Action Log"
      summary={summaryText}
      defaultOpen={false}
    >
      {/* Summary bar */}
      <div className="flex items-center gap-4 text-sm mb-3 pb-3 border-b">
        <span className="text-green-600 font-medium">{found.length}/{actions.length} tools found data</span>
        {errored.length > 0 && (
          <span className="text-destructive font-medium">{errored.length} error{errored.length !== 1 ? 's' : ''}</span>
        )}
        <span className="text-muted-foreground">{(totalTime / 1000).toFixed(1)}s total</span>
      </div>

      {/* Found-data rows */}
      {found.length > 0 && <ActionTable actions={found} />}

      {/* Error rows */}
      {errored.length > 0 && (
        <div className="mt-3">
          <ActionTable actions={errored} isError />
        </div>
      )}

      {/* Collapsed not-found summary */}
      {notFound.length > 0 && <NotFoundSummary actions={notFound} />}
    </CollapsibleCard>
  )
}

function ActionTable({ actions, isError = false }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b">
            <th className="px-3 py-1.5 text-left font-medium text-xs text-muted-foreground">#</th>
            <th className="px-3 py-1.5 text-left font-medium text-xs text-muted-foreground">Tool</th>
            <th className="px-3 py-1.5 text-center font-medium text-xs text-muted-foreground">Found?</th>
            <th className="px-3 py-1.5 text-right font-medium text-xs text-muted-foreground">Facts</th>
            <th className="px-3 py-1.5 text-right font-medium text-xs text-muted-foreground">Latency</th>
            <th className="px-3 py-1.5 text-left font-medium text-xs text-muted-foreground">Summary</th>
          </tr>
        </thead>
        <tbody>
          {actions.map((action, i) => (
            <tr key={i} className="border-b last:border-0">
              <td className="px-3 py-1.5 text-muted-foreground">{action.execution_order || i + 1}</td>
              <td className="px-3 py-1.5 font-medium">{action.tool_name}</td>
              <td className="px-3 py-1.5 text-center">
                {action.data_found ? (
                  <CheckCircle2 className="h-4 w-4 text-green-600 inline" />
                ) : isError ? (
                  <AlertTriangle className="h-4 w-4 text-destructive inline" />
                ) : (
                  <XCircle className="h-4 w-4 text-muted-foreground/50 inline" />
                )}
              </td>
              <td className="px-3 py-1.5 text-right">{action.facts_extracted ?? '-'}</td>
              <td className="px-3 py-1.5 text-right text-muted-foreground">
                {action.latency_ms != null ? `${(action.latency_ms / 1000).toFixed(1)}s` : '-'}
              </td>
              <td className={cn('px-3 py-1.5 text-muted-foreground max-w-xs truncate', isError && 'text-destructive')}>
                {action.error_message || action.result_summary || '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function NotFoundSummary({ actions }) {
  const [expanded, setExpanded] = useState(false)
  const toolNames = actions.map(a => a.tool_name).join(', ')

  return (
    <div className="mt-3 pt-3 border-t">
      <button
        onClick={() => setExpanded(e => !e)}
        className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ChevronRight className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-90')} />
        <span>{actions.length} tool{actions.length !== 1 ? 's' : ''} returned no data</span>
        {!expanded && <span className="text-xs ml-1 truncate max-w-md">({toolNames})</span>}
      </button>
      {expanded && (
        <div className="mt-2 ml-5 space-y-0.5">
          {actions.map((action, i) => (
            <div key={i} className="flex items-center gap-3 text-sm text-muted-foreground">
              <span className="font-medium">{action.tool_name}</span>
              <span className="text-xs">
                {action.latency_ms != null ? `${(action.latency_ms / 1000).toFixed(1)}s` : '-'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
