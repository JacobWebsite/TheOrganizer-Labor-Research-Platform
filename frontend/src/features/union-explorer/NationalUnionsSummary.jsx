import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'

const AFF_GROUPS = [
  { key: 'AFL-CIO', label: 'AFL-CIO', color: '#1a6b5a' },
  { key: 'CTW', label: 'Change to Win', color: '#c78c4e' },
  { key: 'IND', label: 'Independent', color: '#4a90a4' },
]

function groupByAffiliation(data) {
  const groups = { 'AFL-CIO': [], 'CTW': [], 'IND': [] }
  for (const u of data) {
    const abbr = (u.aff_abbr || '').toUpperCase()
    if (abbr === 'AFL-CIO' || abbr.includes('AFL')) groups['AFL-CIO'].push(u)
    else if (abbr === 'CTW' || abbr.includes('CHANGE')) groups['CTW'].push(u)
    else groups['IND'].push(u)
  }
  return groups
}

/**
 * Summary showing 3 affiliation group cards + clickable badges.
 */
export function NationalUnionsSummary({ data, isLoading, onAffiliationClick }) {
  if (isLoading) {
    return (
      <div className="flex gap-4">
        {Array.from({ length: 3 }, (_, i) => (
          <Card key={i} className="flex-1">
            <CardContent className="p-4 space-y-2">
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-7 w-20" />
              <Skeleton className="h-4 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  if (!data || data.length === 0) return null

  const grouped = groupByAffiliation(data)
  const topAffiliations = data.slice(0, 8)

  return (
    <div className="space-y-3">
      <div className="flex gap-4">
        {AFF_GROUPS.map(({ key, label, color }) => {
          const unions = grouped[key] || []
          const members = unions.reduce((s, u) => s + (u.total_members || 0), 0)
          const locals = unions.reduce((s, u) => s + (u.local_count || 0), 0)
          return (
            <Card key={key} className="flex-1" style={{ borderTop: `4px solid ${color}` }}>
              <CardContent className="p-4">
                <p className="font-editorial text-lg font-semibold">{label}</p>
                <p className="text-2xl font-bold tabular-nums" style={{ color }}>{members.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">{locals.toLocaleString()} locals</p>
              </CardContent>
            </Card>
          )
        })}
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
    </div>
  )
}
