import { useNavigate } from 'react-router-dom'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

/**
 * Sister locals table. Row clicks navigate to the local's union profile.
 */
export function SisterLocalsSection({ sisters }) {
  if (!sisters || sisters.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Sister Locals</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No sister locals found.</p>
        </CardContent>
      </Card>
    )
  }

  const navigate = useNavigate()

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">Sister Locals</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">Local Name</th>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">City</th>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">State</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground" title="Dues-paying members (LM filings)">Members</th>
              </tr>
            </thead>
            <tbody>
              {sisters.map((s) => (
                <tr
                  key={s.f_num}
                  className="border-b hover:bg-accent/50 cursor-pointer transition-colors"
                  onClick={() => navigate(`/unions/${s.f_num}`)}
                >
                  <td className="px-3 py-2 font-medium truncate max-w-[280px]">
                    {s.union_name}{s.local_number && s.local_number !== '0' ? ` Local ${s.local_number}` : ''}
                  </td>
                  <td className="px-3 py-2">{s.city || '\u2014'}</td>
                  <td className="px-3 py-2">{s.state || '\u2014'}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatNumber(s.members)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
