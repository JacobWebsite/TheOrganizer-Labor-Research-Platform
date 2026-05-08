import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'

function formatCurrency(n) {
  if (n == null) return '\u2014'
  return '$' + Number(n).toLocaleString()
}

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

function formatRatio(assets, liabilities) {
  if (!liabilities || liabilities === 0) return null
  const ratio = assets / liabilities
  return ratio.toFixed(1) + ':1'
}

/**
 * Balance sheet summary card showing latest year's assets, liabilities, net assets.
 */
function BalanceSheetSummary({ latest }) {
  if (!latest) return null

  const assets = latest.assets
  const liabilities = latest.liabilities
  const netAssets = latest.net_assets
  const ratio = formatRatio(assets, liabilities)
  const hasLiabilities = liabilities != null && liabilities > 0

  return (
    <Card className="mb-4 bg-[#faf6ef]">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-editorial">Balance Sheet ({latest.year})</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Total Assets</p>
            <p className="text-lg tabular-nums font-semibold text-[#3a7d44]">
              {formatCurrency(assets)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Total Liabilities</p>
            {hasLiabilities ? (
              <p className="text-lg tabular-nums font-semibold text-[#c23a22]">
                {formatCurrency(liabilities)}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground italic">No liabilities reported</p>
            )}
          </div>
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Net Assets</p>
            <p className={`text-lg tabular-nums font-bold ${netAssets != null && netAssets < 0 ? 'text-[#c23a22]' : 'text-[#2c2418]'}`}>
              {formatCurrency(netAssets)}
            </p>
          </div>
          {ratio && (
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Asset-to-Liability Ratio</p>
              <p className="text-lg tabular-nums font-semibold text-[#2c2418]">{ratio}</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Financial trends table showing year-over-year members, assets, liabilities, net assets, receipts, and disbursements.
 */
export function UnionFinancialsSection({ trends }) {
  if (!trends || trends.length === 0) return null

  // Latest year is first in array (sorted desc)
  const latest = trends[0]

  return (
    <div className="space-y-0">
      <BalanceSheetSummary latest={latest} />
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Financial Trends</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Year</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground" title="Dues-paying members (LM filings)">Members</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Assets</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Liabilities</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Net Assets</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Receipts</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Disbursements</th>
                </tr>
              </thead>
              <tbody>
                {trends.map((t) => (
                  <tr key={t.year} className="border-b">
                    <td className="px-3 py-2 tabular-nums font-medium">{t.year}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatNumber(t.members)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(t.assets)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(t.liabilities)}</td>
                    <td className={`px-3 py-2 text-right tabular-nums ${t.net_assets != null && t.net_assets < 0 ? 'text-[#c23a22]' : ''}`}>
                      {formatCurrency(t.net_assets)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(t.receipts)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(t.disbursements)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
