import { Flag, ThumbsUp, AlertTriangle, Info } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { ConfidenceDots } from '@/shared/components/ConfidenceDots'

const REASON_BADGE = {
  contradicted: { label: 'Contradicted', className: 'bg-[#c78c4e]/15 text-[#c78c4e] border-[#c78c4e]/30' },
  low_confidence: { label: 'Low Confidence', className: 'bg-[#c23a22]/15 text-[#c23a22] border-[#c23a22]/30' },
  web_numeric: { label: 'Web Numeric', className: 'bg-[#3a6b8c]/15 text-[#3a6b8c] border-[#3a6b8c]/30' },
  low_tool_accuracy: { label: 'Low Tool Accuracy', className: 'bg-[#8a7e6d]/15 text-[#8a7e6d] border-[#8a7e6d]/30' },
}

function PriorityFactRow({ fact, onFlag, onConfirm }) {
  const displayName = fact.display_name || fact.attribute_name?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  const badge = REASON_BADGE[fact.reason] || REASON_BADGE.low_confidence

  return (
    <div className="flex items-center gap-3 py-2 border-b last:border-0 border-muted">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate">{displayName}</span>
          <span className={`inline-flex items-center px-1.5 py-0.5 text-[9px] font-medium rounded border ${badge.className}`}>
            {badge.label}
          </span>
        </div>
        <p className="text-xs text-muted-foreground truncate mt-0.5">
          {fact.attribute_value || '-'}
          {fact.source_name && <span className="ml-2 text-[10px]">via {fact.source_name}</span>}
        </p>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <ConfidenceDots confidence={fact.confidence} />
        {fact.human_verdict == null && (
          <>
            <button
              onClick={() => onConfirm(fact.fact_id)}
              className="p-1 rounded hover:bg-[#3a7d44]/10 text-[#8a7e6d] hover:text-[#3a7d44] transition-colors"
              title="Confirm fact"
              aria-label="Confirm"
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => onFlag(fact.fact_id)}
              className="p-1 rounded hover:bg-[#c23a22]/10 text-[#8a7e6d] hover:text-[#c23a22] transition-colors"
              title="Flag as wrong"
              aria-label="Flag"
            >
              <Flag className="h-3.5 w-3.5" />
            </button>
          </>
        )}
      </div>
    </div>
  )
}

export function PriorityReviewCard({ priorityFacts, onReviewFact, onFlagFact }) {
  if (!priorityFacts || priorityFacts.length === 0) return null

  const unreviewedCount = priorityFacts.filter(f => f.human_verdict == null).length
  if (unreviewedCount === 0) return null

  return (
    <Card className="border-[#c78c4e]/30 bg-[#c78c4e]/5">
      <CardContent className="pt-4">
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="h-4 w-4 text-[#c78c4e]" />
          <h3 className="font-editorial text-sm font-semibold">Review These First</h3>
          <span className="text-[10px] text-muted-foreground">
            {unreviewedCount} fact{unreviewedCount !== 1 ? 's' : ''} need attention
          </span>
          <div className="ml-auto group relative">
            <Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
            <div className="absolute right-0 top-full mt-1 w-56 p-2 bg-card border rounded shadow-lg text-[10px] text-muted-foreground hidden group-hover:block z-20">
              These facts were selected because they are contradicted, low confidence,
              numeric data from web sources, or from tools with low historical accuracy.
              Reviewing them gives the strongest learning signal.
            </div>
          </div>
        </div>
        <div>
          {priorityFacts.map(fact => (
            <PriorityFactRow
              key={fact.fact_id}
              fact={fact}
              onConfirm={(factId) => onReviewFact(factId, 'confirmed')}
              onFlag={(factId) => onFlagFact(factId)}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
