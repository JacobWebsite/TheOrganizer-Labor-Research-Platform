import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'

function formatCurrency(n) {
  if (n == null) return '\u2014'
  return '$' + Number(n).toLocaleString()
}

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

/**
 * Financial trends table showing year-over-year members, assets, and receipts.
 */
export function UnionFinancialsSection({ trends }) {
  if (!trends || trends.length === 0) return null

  return (
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
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Members</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Assets</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Receipts</th>
              </tr>
            </thead>
            <tbody>
              {trends.map((t) => (
                <tr key={t.year} className="border-b">
                  <td className="px-3 py-2 tabular-nums font-medium">{t.year}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatNumber(t.members)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(t.assets)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(t.receipts)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
