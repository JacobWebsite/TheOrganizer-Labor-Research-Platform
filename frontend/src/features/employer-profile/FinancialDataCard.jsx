import { TrendingUp, AlertTriangle } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { SourceAttribution } from '@/shared/components/SourceAttribution'
import { DataSourceBadge } from '@/shared/components/DataSourceBadge'

function formatCurrency(n) {
  if (n == null) return '\u2014'
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : ''
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`
  return `${sign}$${abs.toLocaleString()}`
}

function YoyChange({ value }) {
  if (value == null) return null
  const color = value >= 0 ? 'text-[#3a7d44]' : 'text-[#c23a22]'
  const prefix = value >= 0 ? '+' : ''
  return <span className={`text-xs ${color}`}>{prefix}{value.toFixed(1)}% YoY</span>
}

export function FinancialDataCard({ scorecard, dataSources, financials, sourceAttribution }) {
  const growthPct = scorecard?.bls_growth_pct
  const isPublic = dataSources?.is_public
  const ticker = dataSources?.ticker
  const isFedContractor = dataSources?.is_federal_contractor
  const has990 = dataSources?.has_990
  const financialScore = scorecard?.score_financial

  const hasSec = financials?.has_sec_financials
  const has990Financials = financials?.has_990_financials

  // Show amber warning if no meaningful data at all
  if (
    growthPct == null &&
    !isPublic &&
    !isFedContractor &&
    !has990 &&
    financialScore == null &&
    !hasSec &&
    !has990Financials
  ) {
    return (
      <CollapsibleCard icon={TrendingUp} title="Financial Data" summary="No records matched">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No financial data has been matched to this employer. This does <strong>not</strong> mean
            no financial records exist -- it may mean our matching has not yet connected this employer to
            SEC filings, IRS 990 data, or BLS industry statistics.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  // Build summary text: prefer revenue, fall back to growth %
  const latest = financials?.latest
  let summary = 'Financial overview'
  if (hasSec && latest?.revenue != null) {
    summary = `Revenue: ${formatCurrency(latest.revenue)}`
  } else if (growthPct != null) {
    summary = `Industry growth: ${Number(growthPct).toFixed(1)}%`
  }

  return (
    <CollapsibleCard icon={TrendingUp} title="Financial Data" summary={summary}>
      <div className="space-y-4">
        <SourceAttribution attribution={sourceAttribution} />
        {dataSources && (
          <div className="flex flex-wrap gap-2">
            <DataSourceBadge
              source="990"
              hasFlag={dataSources.has_990}
              hasData={scorecard?.n990_revenue != null || has990Financials}
            />
            <DataSourceBadge
              source="SEC"
              hasFlag={dataSources.has_sec}
              hasData={dataSources.is_public || hasSec}
            />
          </div>
        )}

        {/* SEC Financial Detail */}
        {hasSec && latest && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <span className="font-editorial text-sm font-semibold text-foreground">
                {financials.sec_company?.company_name || 'SEC Filing'}
              </span>
              {financials.sec_company?.ticker && (
                <span className="rounded bg-[#6b5b8a]/10 px-1.5 py-0.5 text-xs font-medium text-[#6b5b8a]">
                  {financials.sec_company.ticker}
                </span>
              )}
            </div>

            {/* Primary metrics: Revenue, Net Income, Total Assets */}
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Revenue</span>
                <div className="font-medium">{formatCurrency(latest.revenue)}</div>
                <YoyChange value={financials.revenue_growth_pct} />
              </div>
              <div>
                <span className="text-muted-foreground">Net Income</span>
                <div className="font-medium">{formatCurrency(latest.net_income)}</div>
                <YoyChange value={financials.income_growth_pct} />
              </div>
              <div>
                <span className="text-muted-foreground">Total Assets</span>
                <div className="font-medium">{formatCurrency(latest.total_assets)}</div>
              </div>
            </div>

            {/* Secondary metrics: Liabilities, Long-term Debt */}
            <div className="grid grid-cols-2 gap-4 text-sm">
              {latest.total_liabilities != null && (
                <div>
                  <span className="text-muted-foreground">Total Liabilities</span>
                  <div className="font-medium">{formatCurrency(latest.total_liabilities)}</div>
                </div>
              )}
              {latest.long_term_debt != null && (
                <div>
                  <span className="text-muted-foreground">Long-term Debt</span>
                  <div className="font-medium">{formatCurrency(latest.long_term_debt)}</div>
                </div>
              )}
            </div>

            {/* Profit margin bar */}
            {latest.profit_margin != null && (
              <div className="text-sm">
                <span className="text-muted-foreground">Profit Margin</span>
                <div className="flex items-center gap-2 mt-1">
                  <div className="flex-1 h-2 bg-muted rounded overflow-hidden">
                    <div
                      className="h-full rounded bg-[#1a6b5a]"
                      style={{ width: `${Math.min(Math.max(latest.profit_margin, 0), 100)}%` }}
                    />
                  </div>
                  <span className="text-xs font-medium w-10">{latest.profit_margin.toFixed(1)}%</span>
                </div>
              </div>
            )}

            {/* Employee count */}
            {latest.employee_count != null && (
              <div className="text-sm">
                <span className="text-muted-foreground">SEC Reported Employees</span>
                <div className="font-medium">{Number(latest.employee_count).toLocaleString()}</div>
              </div>
            )}

            {/* Revenue trend */}
            {financials.trends?.length > 1 && (
              <div className="text-sm">
                <span className="text-muted-foreground">Revenue Trend</span>
                <div className="mt-1 space-y-1">
                  {financials.trends.map((t) => (
                    <div key={t.fiscal_year_end} className="flex justify-between text-xs">
                      <span className="text-muted-foreground">
                        FY {t.fiscal_year_end?.slice(0, 4)}
                      </span>
                      <span className="font-medium">{formatCurrency(t.revenue)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {latest.fiscal_year_end && (
              <p className="text-xs text-muted-foreground">
                Data as of fiscal year ending {latest.fiscal_year_end}
              </p>
            )}
          </div>
        )}

        {/* 990 Financials fallback (only if no SEC) */}
        {has990Financials && !hasSec && financials.n990_fallback && (
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-4 text-sm">
              {financials.n990_fallback.revenue != null && (
                <div>
                  <span className="text-muted-foreground">Revenue</span>
                  <div className="font-medium">{formatCurrency(financials.n990_fallback.revenue)}</div>
                </div>
              )}
              {financials.n990_fallback.assets != null && (
                <div>
                  <span className="text-muted-foreground">Assets</span>
                  <div className="font-medium">{formatCurrency(financials.n990_fallback.assets)}</div>
                </div>
              )}
              {financials.n990_fallback.expenses != null && (
                <div>
                  <span className="text-muted-foreground">Expenses</span>
                  <div className="font-medium">{formatCurrency(financials.n990_fallback.expenses)}</div>
                </div>
              )}
            </div>
            <p className="text-xs text-muted-foreground">Source: IRS Form 990</p>
          </div>
        )}

        {/* Existing scorecard-derived fields -- always shown when available */}
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
