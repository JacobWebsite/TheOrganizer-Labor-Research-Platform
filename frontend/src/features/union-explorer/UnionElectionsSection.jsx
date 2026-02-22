import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

function formatPercent(n) {
  if (n == null) return '\u2014'
  return (n * 100).toFixed(0) + '%'
}

/**
 * NLRB elections section with summary stats and elections table.
 */
export function UnionElectionsSection({ elections }) {
  if (!elections) return null

  const summary = elections.summary || elections
  const list = elections.elections || []
  const hasData = summary.wins != null || summary.losses != null || list.length > 0

  if (!hasData) return null

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">NLRB Elections</CardTitle>
      </CardHeader>
      <CardContent>
        {/* Summary stats */}
        <div className="flex flex-wrap gap-x-8 gap-y-2 mb-4">
          <div>
            <p className="text-2xl font-bold tabular-nums text-green-700">{formatNumber(summary.wins)}</p>
            <p className="text-xs text-muted-foreground">Wins</p>
          </div>
          <div>
            <p className="text-2xl font-bold tabular-nums text-red-700">{formatNumber(summary.losses)}</p>
            <p className="text-xs text-muted-foreground">Losses</p>
          </div>
          <div>
            <p className="text-2xl font-bold tabular-nums">{formatPercent(summary.win_rate)}</p>
            <p className="text-xs text-muted-foreground">Win rate</p>
          </div>
        </div>

        {/* Elections table */}
        {list.length > 0 && (
          <div className="overflow-x-auto border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Date</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Employer</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Unit Size</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Result</th>
                </tr>
              </thead>
              <tbody>
                {list.map((el, idx) => {
                  const isWon = el.result?.toLowerCase() === 'won' || el.result?.toLowerCase() === 'certified'
                  const isLost = el.result?.toLowerCase() === 'lost' || el.result?.toLowerCase() === 'dismissed'
                  return (
                    <tr key={idx} className="border-b">
                      <td className="px-3 py-2 tabular-nums">{el.date || '\u2014'}</td>
                      <td className="px-3 py-2 truncate max-w-[240px]">{el.employer || '\u2014'}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{formatNumber(el.unit_size)}</td>
                      <td className="px-3 py-2">
                        {el.result ? (
                          <Badge
                            className={
                              isWon ? 'bg-green-100 text-green-800' :
                              isLost ? 'bg-red-100 text-red-800' :
                              'bg-gray-100 text-gray-800'
                            }
                          >
                            {el.result}
                          </Badge>
                        ) : '\u2014'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
