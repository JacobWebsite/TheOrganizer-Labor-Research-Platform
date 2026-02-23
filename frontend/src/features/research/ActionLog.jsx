import { Terminal, CheckCircle2, XCircle } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { cn } from '@/lib/utils'

export function ActionLog({ actions }) {
  if (!actions || actions.length === 0) return null

  const summary = `${actions.length} tool${actions.length !== 1 ? 's' : ''} called`

  return (
    <CollapsibleCard
      icon={Terminal}
      title="Action Log"
      summary={summary}
      defaultOpen={false}
    >
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
                  ) : (
                    <XCircle className="h-4 w-4 text-muted-foreground/50 inline" />
                  )}
                </td>
                <td className="px-3 py-1.5 text-right">{action.facts_extracted ?? '-'}</td>
                <td className="px-3 py-1.5 text-right text-muted-foreground">
                  {action.latency_ms != null ? `${(action.latency_ms / 1000).toFixed(1)}s` : '-'}
                </td>
                <td className={cn('px-3 py-1.5 text-muted-foreground max-w-xs truncate', action.error_message && 'text-destructive')}>
                  {action.error_message || action.result_summary || '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CollapsibleCard>
  )
}
