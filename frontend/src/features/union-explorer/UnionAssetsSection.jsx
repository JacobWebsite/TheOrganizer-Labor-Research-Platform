import { useState } from 'react'
import { Landmark, ChevronRight } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { useUnionAssets } from '@/shared/api/unions'

function formatCurrency(n) {
  if (n == null) return '\u2014'
  return '$' + Number(n).toLocaleString()
}

/**
 * Expandable investment group showing holdings.
 */
function InvestmentGroup({ name, group }) {
  const [open, setOpen] = useState(false)
  const holdings = group.holdings || []

  return (
    <div className="border rounded-md overflow-hidden">
      <button
        type="button"
        className="flex items-center justify-between w-full px-4 py-3 text-left hover:bg-[#ede7db]/50 transition-colors"
        onClick={() => setOpen((prev) => !prev)}
      >
        <div className="flex items-center gap-2">
          <ChevronRight className={`h-4 w-4 text-muted-foreground transition-transform ${open ? 'rotate-90' : ''}`} />
          <span className="text-sm font-medium text-[#2c2418]">{name}</span>
          <span className="text-xs text-muted-foreground">({holdings.length} holding{holdings.length !== 1 ? 's' : ''})</span>
        </div>
        <span className="text-sm tabular-nums font-semibold text-[#2c2418]">{formatCurrency(group.total)}</span>
      </button>
      {open && holdings.length > 0 && (
        <div className="border-t bg-[#faf6ef]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="px-4 py-1.5 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Holding</th>
                <th className="px-4 py-1.5 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">Amount</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((h, i) => (
                <tr key={i} className="border-b last:border-b-0">
                  <td className="px-4 py-1.5 text-[#2c2418]">{h.name || '\u2014'}</td>
                  <td className="px-4 py-1.5 text-right tabular-nums">{formatCurrency(h.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/**
 * Asset holdings section for union profile.
 * Fetches investment groups and individual holdings from the assets endpoint.
 */
export function UnionAssetsSection({ fileNumber }) {
  const { data, isLoading } = useUnionAssets(fileNumber)

  if (isLoading) return null

  const groups = data?.investment_groups || {}
  const groupEntries = Object.entries(groups)
  const totalHoldings = data?.total_holdings || 0
  const holdingsYear = data?.holdings_year
  const summaryYear = data?.summary?.year
  const yearMismatch = data?.year_mismatch

  const holdingsSummary = totalHoldings > 0
    ? `${totalHoldings} holding${totalHoldings !== 1 ? 's' : ''} across ${groupEntries.length} group${groupEntries.length !== 1 ? 's' : ''}`
    : 'No holdings'

  const summaryText = holdingsYear
    ? `${holdingsSummary} (from ${holdingsYear} filing)`
    : holdingsSummary

  return (
    <CollapsibleCard
      icon={Landmark}
      title="Asset Holdings"
      summary={summaryText}
      defaultOpen={false}
      storageKey="union-assets-section"
    >
      {yearMismatch && (
        <div className="mb-3 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <strong>Filing year note:</strong> Detailed holdings below are from the {holdingsYear} filing
          (the most recent year with itemized schedule&nbsp;7/8 detail). Aggregate totals shown
          elsewhere on this page are from {summaryYear}, the most recent filing overall. This
          union's {summaryYear} filing did not include itemized investment detail.
        </div>
      )}
      {groupEntries.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No detailed investment data available. This union may file LM-3 or LM-4 (simplified forms without investment detail).
        </p>
      ) : (
        <div className="space-y-2">
          {groupEntries.map(([name, group]) => (
            <InvestmentGroup key={name} name={name} group={group} />
          ))}
        </div>
      )}
      <p className="mt-4 text-xs text-muted-foreground italic">
        Liability breakdown is not available in LM filings. Only aggregate total liabilities are reported.
      </p>
    </CollapsibleCard>
  )
}
