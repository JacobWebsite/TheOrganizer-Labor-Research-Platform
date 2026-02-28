import { TrendingUp } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { SourceAttribution } from '@/shared/components/SourceAttribution'

export function FinancialDataCard({ scorecard, dataSources, sourceAttribution }) {
  const growthPct = scorecard?.bls_growth_pct
  const isPublic = dataSources?.is_public
  const ticker = dataSources?.ticker
  const isFedContractor = dataSources?.is_federal_contractor
  const has990 = dataSources?.has_990
  const financialScore = scorecard?.score_financial

  // Hide if no meaningful data
  if (growthPct == null && !isPublic && !isFedContractor && !has990 && financialScore == null) return null

  const summary = growthPct != null ? `Industry growth: ${Number(growthPct).toFixed(1)}%` : 'Financial overview'

  return (
    <CollapsibleCard icon={TrendingUp} title="Financial Data" summary={summary}>
      <div className="space-y-4">
        <SourceAttribution attribution={sourceAttribution} />
        <div className="grid grid-cols-2 gap-4 text-sm">
        {growthPct != null && (
          <div>
            <span className="text-muted-foreground">BLS Industry Growth</span>
            <div className="font-medium">{Number(growthPct).toFixed(1)}%</div>
          </div>
        )}
        {isPublic != null && (
          <div>
            <span className="text-muted-foreground">Public Company</span>
            <div className="font-medium">{isPublic ? `Yes${ticker ? ` (${ticker})` : ''}` : 'No'}</div>
          </div>
        )}
        {isFedContractor != null && (
          <div>
            <span className="text-muted-foreground">Federal Contractor</span>
            <div className="font-medium">{isFedContractor ? 'Yes' : 'No'}</div>
          </div>
        )}
        {has990 != null && (
          <div>
            <span className="text-muted-foreground">Nonprofit (990)</span>
            <div className="font-medium">{has990 ? 'Yes' : 'No'}</div>
          </div>
        )}
        {financialScore != null && (
          <div className="col-span-2">
            <span className="text-muted-foreground">Financial Score</span>
            <div className="flex items-center gap-2 mt-1">
              <div className="flex-1 h-2 bg-muted overflow-hidden">
                <div className="h-full bg-red-400" style={{ width: `${(financialScore / 10) * 100}%` }} />
              </div>
              <span className="text-xs font-medium w-8">{Number(financialScore).toFixed(1)}</span>
            </div>
          </div>
        )}
        </div>
      </div>
    </CollapsibleCard>
  )
}
