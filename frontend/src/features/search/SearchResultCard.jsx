import { useNavigate } from 'react-router-dom'
import { MapPin, Users } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { SourceBadge } from './SourceBadge'

function formatNumber(n) {
  if (n == null) return null
  return Number(n).toLocaleString()
}

export function SearchResultCard({ employer }) {
  const navigate = useNavigate()
  const workers = employer.consolidated_workers || employer.unit_size
  const location = [employer.city, employer.state].filter(Boolean).join(', ')

  return (
    <Card
      className="cursor-pointer hover:bg-accent/50 transition-colors"
      onClick={() => navigate(`/employers/${employer.canonical_id}`)}
    >
      <CardContent className="p-4 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="font-medium leading-tight">
            {employer.employer_name}
            {employer.group_member_count > 1 && (
              <span className="ml-1.5 text-xs text-muted-foreground">
                ({employer.group_member_count} locations)
              </span>
            )}
          </div>
          <SourceBadge source={employer.source_type} />
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {location && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" /> {location}
            </span>
          )}
          {workers != null && (
            <span className="inline-flex items-center gap-1">
              <Users className="h-3 w-3" /> {formatNumber(workers)} workers
            </span>
          )}
        </div>
        {employer.union_name && (
          <div className="text-xs text-muted-foreground truncate">
            Union: {employer.union_name}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
