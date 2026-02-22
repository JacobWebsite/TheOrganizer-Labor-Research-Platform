import { Link2 } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { SourceBadge } from '@/features/search/SourceBadge'

function formatDate(d) {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return d
  }
}

export function CrossReferencesSection({ crossReferences }) {
  if (!crossReferences || crossReferences.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Link2 className="h-5 w-5 text-muted-foreground" />
          <CardTitle>Cross-References</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">Source</th>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">Name</th>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">Location</th>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">Case / ID</th>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">Date</th>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">Result</th>
              </tr>
            </thead>
            <tbody>
              {crossReferences.map((ref, i) => (
                <tr key={ref.id || ref.case_number || i} className="border-b">
                  <td className="px-3 py-2">
                    <SourceBadge source={ref.source_type || ref.source} />
                  </td>
                  <td className="px-3 py-2 font-medium truncate max-w-[200px]">
                    {ref.employer_name || ref.participant_name || ref.name || '—'}
                  </td>
                  <td className="px-3 py-2">
                    {[ref.city || ref.unit_city, ref.state || ref.unit_state].filter(Boolean).join(', ') || '—'}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{ref.case_number || ref.id || '—'}</td>
                  <td className="px-3 py-2">{formatDate(ref.date || ref.election_date || ref.date_filed)}</td>
                  <td className="px-3 py-2">{ref.result || ref.status || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
