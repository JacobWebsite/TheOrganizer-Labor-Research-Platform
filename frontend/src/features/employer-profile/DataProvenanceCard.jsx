import { Link2 } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { ConfidenceDots } from '@/shared/components/ConfidenceDots'

const SOURCE_COLORS = {
  osha: 'bg-amber-100 text-amber-800 border-amber-300',
  whd: 'bg-rose-100 text-rose-800 border-rose-300',
  nlrb: 'bg-blue-100 text-blue-800 border-blue-300',
  sec: 'bg-purple-100 text-purple-800 border-purple-300',
  bmf: 'bg-green-100 text-green-800 border-green-300',
  sam: 'bg-cyan-100 text-cyan-800 border-cyan-300',
  corpwatch: 'bg-orange-100 text-orange-800 border-orange-300',
  mergent: 'bg-indigo-100 text-indigo-800 border-indigo-300',
}

export function DataProvenanceCard({ matchSummary }) {
  if (!matchSummary || matchSummary.length === 0) return null

  const summary = `${matchSummary.length} source${matchSummary.length === 1 ? '' : 's'} linked`

  return (
    <CollapsibleCard icon={Link2} title="Data Provenance" summary={summary}>
      <div className="space-y-3">
        {matchSummary.map((entry) => {
          const colorClass = SOURCE_COLORS[entry.source_system] || 'bg-muted text-muted-foreground border-border'
          return (
            <div key={entry.source_system} className="flex items-start gap-3 text-sm">
              <span className={`inline-flex items-center px-2 py-0.5 text-xs font-semibold uppercase border shrink-0 ${colorClass}`}>
                {entry.source_system}
              </span>
              <div className="flex-1 min-w-0">
                <div className="font-medium">{entry.source_label}</div>
                <div className="text-muted-foreground text-xs mt-0.5">{entry.citation}</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {entry.match_count > 1 && (
                  <span className="text-xs text-muted-foreground">{entry.match_count} records</span>
                )}
                <ConfidenceDots
                  confidence={entry.best_confidence_score != null ? entry.best_confidence_score : entry.best_confidence}
                  matchTier={entry.best_match_tier}
                />
              </div>
            </div>
          )
        })}
      </div>
    </CollapsibleCard>
  )
}
