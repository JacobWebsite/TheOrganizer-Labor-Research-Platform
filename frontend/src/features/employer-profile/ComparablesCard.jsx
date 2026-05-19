import { Users, AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useEmployerComparables } from '@/shared/api/profile'

// ComparablesCard surfaces F7-side strategic peers (similar union/non-union
// employers ranked by similarity_pct). Distinct from CompetitorsCard which
// is the NAICS+size industry-peer view.
//
// Polish-sweep states (Week 4 A.3):
//  - Loading: skeleton placeholder mirroring final 5-column layout
//  - Error:   amber panel with Retry button (calls refetch)
//  - Empty:   "no comparables found" panel with explanation of why
//  - Populated: 5-column similarity table

export function ComparablesCard({ employerId }) {
  const { data, isLoading, isError, refetch } = useEmployerComparables(employerId)

  // Loading: skeleton placeholder so users see the card is on its way.
  if (isLoading) {
    return (
      <CollapsibleCard
        icon={Users}
        title="Comparable Employers"
        summary="Loading..."
        defaultOpen
      >
        <div className="space-y-3" data-testid="comparables-card-skeleton">
          <Skeleton className="h-4 w-64" />
          <div className="border">
            <div className="border-b bg-muted/50 px-2 py-1.5">
              <Skeleton className="h-3 w-32" />
            </div>
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-3 border-b px-2 py-2">
                <Skeleton className="h-3 w-6" />
                <Skeleton className="h-3 w-40 flex-1" />
                <Skeleton className="h-3 w-12" />
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-3 w-16" />
              </div>
            ))}
          </div>
        </div>
      </CollapsibleCard>
    )
  }

  // Error: amber panel + retry button. Distinct from "no data" so users see
  // this is a transient problem, not a known absence of records.
  if (isError) {
    return (
      <CollapsibleCard
        icon={Users}
        title="Comparable Employers"
        summary="Error loading data"
        defaultOpen
      >
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <div className="flex-1">
            <p className="mb-2">Could not load comparable employers. Try again or check back shortly.</p>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        </div>
      </CollapsibleCard>
    )
  }

  const comparables = data?.comparables || []

  // Empty: matched employer but no comparables found. Render an explicit panel
  // so users see the card is intentionally empty, not hidden. Critical for the
  // "no data" vs "no matches" UX distinction.
  if (comparables.length === 0) {
    return (
      <CollapsibleCard
        icon={Users}
        title="Comparable Employers"
        summary="No comparables found"
      >
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No comparable employers were found for this employer. This does <strong>not</strong>{' '}
            mean none exist &mdash; comparables are derived from the F7 union-relations corpus
            (NAICS, state, workforce-size similarity), so private companies and employers
            without F7 ties may appear empty here.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  // Backend returns `comparable_type` = 'union' | 'non_union' (not `union_name`).
  // Count union-side comparables for the header chip.
  const unionized = comparables.filter((c) => c.comparable_type === 'union').length

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
              <th className="px-2 py-1.5 text-left font-medium">Union Status</th>
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
                <td className="px-2 py-1.5">
                  {c.comparable_type === 'union' ? (
                    <span className="inline-flex px-1.5 py-0.5 text-[10px] bg-green-100 text-green-800 border">
                      Union
                    </span>
                  ) : c.comparable_type === 'non_union' ? (
                    <span className="inline-flex px-1.5 py-0.5 text-[10px] bg-stone-100 text-stone-700 border">
                      Non-union
                    </span>
                  ) : (
                    <span className="text-muted-foreground">--</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CollapsibleCard>
  )
}
