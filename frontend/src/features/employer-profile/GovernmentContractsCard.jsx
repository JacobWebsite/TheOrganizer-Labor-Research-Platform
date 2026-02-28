import { FileText } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { SourceAttribution } from '@/shared/components/SourceAttribution'

function formatCurrency(n) {
  if (n == null) return '$0'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}

export function GovernmentContractsCard({ dataSources, sourceAttribution }) {
  if (!dataSources?.is_federal_contractor) return null

  const obligations = dataSources.federal_obligations
  const contractCount = dataSources.federal_contract_count

  const summary = obligations
    ? `${formatCurrency(obligations)} across ${contractCount || 0} contracts`
    : 'Federal contractor'

  return (
    <CollapsibleCard icon={FileText} title="Government Contracts" summary={summary}>
      <div className="space-y-4">
        <SourceAttribution attribution={sourceAttribution} />
        <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-muted-foreground">Total Obligations</span>
          <div className="font-medium">{formatCurrency(obligations)}</div>
        </div>
        {contractCount != null && (
          <div>
            <span className="text-muted-foreground">Contract Count</span>
            <div className="font-medium">{Number(contractCount).toLocaleString()}</div>
          </div>
        )}
        <div className="col-span-2">
          <span className="inline-flex items-center px-2 py-0.5 text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
            Federal Contractor
          </span>
        </div>
      </div>
      </div>
    </CollapsibleCard>
  )
}
