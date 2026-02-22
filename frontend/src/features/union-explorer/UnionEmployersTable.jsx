import { useNavigate } from 'react-router-dom'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

/**
 * Simple table of top employers for a union. Row clicks navigate to employer profile.
 */
export function UnionEmployersTable({ employers }) {
  const navigate = useNavigate()

  if (!employers || employers.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Employers</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No employer data available.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">Employers</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">Employer</th>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">City</th>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">State</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Workers</th>
              </tr>
            </thead>
            <tbody>
              {employers.map((emp) => (
                <tr
                  key={emp.f7_employer_id || emp.employer_name}
                  className="border-b hover:bg-accent/50 cursor-pointer transition-colors"
                  onClick={() => {
                    if (emp.f7_employer_id) {
                      navigate(`/employers/${emp.f7_employer_id}`)
                    }
                  }}
                >
                  <td className="px-3 py-2 font-medium truncate max-w-[280px]">
                    {emp.employer_name || '\u2014'}
                  </td>
                  <td className="px-3 py-2">{emp.city || '\u2014'}</td>
                  <td className="px-3 py-2">{emp.state || '\u2014'}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatNumber(emp.workers)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
