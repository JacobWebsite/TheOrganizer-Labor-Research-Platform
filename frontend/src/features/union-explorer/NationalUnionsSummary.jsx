import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'

/**
 * Summary card showing national union overview: totals and top affiliation chips.
 */
export function NationalUnionsSummary({ data, isLoading, onAffiliationClick }) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <Skeleton className="h-6 w-48" />
        </CardHeader>
        <CardContent>
          <div className="flex gap-8 mb-3">
            <Skeleton className="h-7 w-20" />
            <Skeleton className="h-7 w-24" />
          </div>
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-7 w-20" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!data || data.length === 0) return null

  const totalLocals = data.reduce((sum, u) => sum + (u.local_count || 0), 0)
  const totalMembers = data.reduce((sum, u) => sum + (u.total_members || 0), 0)
  const topAffiliations = data.slice(0, 8)

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">National Unions Overview</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex gap-8 mb-4">
          <div>
            <p className="text-2xl font-bold tabular-nums">{totalLocals.toLocaleString()}</p>
            <p className="text-xs text-muted-foreground">Total locals</p>
          </div>
          <div>
            <p className="text-2xl font-bold tabular-nums">{totalMembers.toLocaleString()}</p>
            <p className="text-xs text-muted-foreground">Total members</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {topAffiliations.map((a) => (
            <button
              key={a.aff_abbr}
              type="button"
              onClick={() => onAffiliationClick(a.aff_abbr)}
              className="cursor-pointer"
            >
              <Badge variant="secondary" className="hover:bg-primary hover:text-primary-foreground transition-colors">
                {a.aff_abbr}
                <span className="ml-1 text-[10px] opacity-70">
                  {(a.total_members || 0).toLocaleString()}
                </span>
              </Badge>
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
