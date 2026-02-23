import { Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { useEmployerComparables } from '@/shared/api/profile'

export function ComparablesCard({ employerId }) {
  const { data, isLoading } = useEmployerComparables(employerId)

  if (isLoading) return null
  if (!data?.comparables?.length) return null

  const comparables = data.comparables
  const unionized = comparables.filter((c) => c.union_name).length

  return (
    <CollapsibleCard
      icon={Users}
      title="Comparable Employers"
      summary={`${comparables.length} comparable employers · ${unionized} unionized`}
    >
      <div className="overflow-x-auto border">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-2 py-1.5 text-left font-medium">#</th>
              <th className="px-2 py-1.5 text-left font-medium">Employer</th>
              <th className="px-2 py-1.5 text-right font-medium">Similarity</th>
              <th className="px-2 py-1.5 text-left font-medium">Match Reasons</th>
              <th className="px-2 py-1.5 text-left font-medium">Union</th>
            </tr>
          </thead>
          <tbody>
            {comparables.map((c) => (
              <tr key={c.rank} className="border-b">
                <td className="px-2 py-1.5 text-muted-foreground">{c.rank}</td>
                <td className="px-2 py-1.5 font-medium">
                  {c.comparable_id ? (
                    <Link to={`/employers/MASTER-${c.comparable_id}`} className="text-primary hover:underline">
                      {c.comparable_name}
                    </Link>
                  ) : c.comparable_name}
                </td>
                <td className="px-2 py-1.5 text-right font-medium">{c.similarity_pct}%</td>
                <td className="px-2 py-1.5">
                  <div className="flex flex-wrap gap-1">
                    {(c.match_reasons || []).slice(0, 3).map((r, i) => (
                      <span key={i} className="inline-flex px-1.5 py-0.5 text-[10px] bg-stone-100 text-stone-600 border">
                        {r}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-2 py-1.5">{c.union_name || <span className="text-muted-foreground">--</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CollapsibleCard>
  )
}
