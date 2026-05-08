import { FileText, AlertTriangle } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { SourceAttribution } from '@/shared/components/SourceAttribution'
import { DataSourceBadge } from '@/shared/components/DataSourceBadge'

function formatCurrency(n) {
  if (n == null) return '$0'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}

function formatNumber(n) {
  if (n == null) return '0'
  return Number(n).toLocaleString()
}

/**
 * Government contracts card. Shows federal (SAM.gov) and state/local
 * (NY/VA/OH 11-source pipeline) sections side-by-side.
 *
 * R7-8 (2026-04-27): Previously short-circuited to "no records matched"
 * unless `is_federal_contractor`. Now renders state/local section alongside
 * (or independently from) federal. The card returns null only when BOTH
 * federal and state/local are absent.
 *
 * State/local total_contract_amount is intentionally NOT displayed --
 * source-side typos (NY ABO $1.2Q, NYC Awards $97T) make the dollar values
 * unreliable. Display source_count + contract_row_count instead.
 */
export function GovernmentContractsCard({ dataSources, sourceAttribution }) {
  const isFederal = !!dataSources?.is_federal_contractor
  const isStateLocal = !!dataSources?.is_state_local_contractor

  if (!isFederal && !isStateLocal) {
    return (
      <CollapsibleCard icon={FileText} title="Government Contracts" summary="No records matched">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No government contract data has been matched to this employer. This does <strong>not</strong> mean
            the employer has no contracts &mdash; it may mean our matching has not yet connected this employer
            to SAM.gov or state/local contract records.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  const obligations = dataSources.federal_obligations
  const contractCount = dataSources.federal_contract_count
  const stateLocalCount = dataSources.state_local_contract_count
  const stateLocalSourceCount = dataSources.state_local_source_count

  const summaryParts = []
  if (isFederal) {
    summaryParts.push(
      obligations
        ? `Federal: ${formatCurrency(obligations)} / ${contractCount || 0} contracts`
        : 'Federal contractor'
    )
  }
  if (isStateLocal) {
    summaryParts.push(
      `State/Local: ${formatNumber(stateLocalCount)} contracts across ${stateLocalSourceCount || 0} sources`
    )
  }
  const summary = summaryParts.join(' · ')

  return (
    <CollapsibleCard icon={FileText} title="Government Contracts" summary={summary}>
      <div className="space-y-4">
        <SourceAttribution attribution={sourceAttribution} />

        {isFederal && (
          <div className="space-y-3 border-l-2 border-blue-200 pl-3">
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-semibold">Federal Contracts</h4>
              <DataSourceBadge
                source="SAM"
                hasFlag={dataSources?.has_sam || dataSources?.is_federal_contractor}
                hasData={!!dataSources?.federal_obligations}
              />
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Total Obligations</span>
                <div className="font-medium">{formatCurrency(obligations)}</div>
              </div>
              {contractCount != null && (
                <div>
                  <span className="text-muted-foreground">Contract Count</span>
                  <div className="font-medium">{formatNumber(contractCount)}</div>
                </div>
              )}
              <div className="col-span-2">
                <span className="inline-flex items-center px-2 py-0.5 text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
                  Federal Contractor
                </span>
              </div>
            </div>
          </div>
        )}

        {isStateLocal && (
          <div className="space-y-3 border-l-2 border-teal-200 pl-3">
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-semibold">State &amp; Local Contracts</h4>
              <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-semibold bg-teal-50 text-teal-700 border border-teal-200">
                NY / VA / OH
              </span>
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Contract Records</span>
                <div className="font-medium">{formatNumber(stateLocalCount)}</div>
              </div>
              <div>
                <span className="text-muted-foreground">Source Tables</span>
                <div className="font-medium">{stateLocalSourceCount || 0}</div>
              </div>
              <div className="col-span-2">
                <span className="inline-flex items-center px-2 py-0.5 text-xs font-medium bg-teal-50 text-teal-700 border border-teal-200">
                  State / Local Contractor
                </span>
              </div>
              <p className="col-span-2 text-xs text-muted-foreground">
                Aggregated from 11 NY/VA/OH state and city contract sources. Dollar amounts are
                unreliable across sources (known typos at the source) and are intentionally
                hidden; trust contract count and source count.
              </p>
            </div>
          </div>
        )}
      </div>
    </CollapsibleCard>
  )
}
