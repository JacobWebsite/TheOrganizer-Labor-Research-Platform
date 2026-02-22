import { Link } from 'react-router-dom'
import { ArrowLeft, MapPin, Users, Building2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

/**
 * Header component for union profile page. Shows name, affiliation, sector,
 * location, and key counts.
 */
export function UnionProfileHeader({ union }) {
  if (!union) return null

  const location = [union.city, union.state].filter(Boolean).join(', ')

  return (
    <div className="space-y-3">
      <Link
        to="/unions"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Unions
      </Link>

      <div>
        <h1 className="text-2xl font-bold">{union.union_name || '\u2014'}</h1>

        <div className="flex flex-wrap items-center gap-2 mt-2">
          {union.aff_abbr && (
            <Badge variant="default">{union.aff_abbr}</Badge>
          )}
          {union.sector && (
            <Badge variant="outline">{union.sector}</Badge>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
        {location && (
          <span className="inline-flex items-center gap-1">
            <MapPin className="h-4 w-4" />
            {location}
          </span>
        )}
        {union.members != null && (
          <span className="inline-flex items-center gap-1">
            <Users className="h-4 w-4" />
            {Number(union.members).toLocaleString()} members
          </span>
        )}
        {union.employer_count != null && (
          <span className="inline-flex items-center gap-1">
            <Building2 className="h-4 w-4" />
            {Number(union.employer_count).toLocaleString()} employers
          </span>
        )}
      </div>
    </div>
  )
}
