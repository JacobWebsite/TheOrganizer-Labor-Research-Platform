import { Landmark } from 'lucide-react'
import { Link } from 'react-router-dom'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'

export function UnionRelationshipsCard({ employer }) {
  const unionName = employer?.latest_union_name || employer?.union_name
  if (!unionName) return null

  const fnum = employer?.latest_union_fnum || employer?.union_fnum
  const unitSize = employer?.latest_unit_size || employer?.unit_size
  const noticeDate = employer?.latest_notice_date
  const affAbbr = employer?.aff_abbr

  return (
    <CollapsibleCard
      icon={Landmark}
      title="Union Relationships"
      summary={`Represented by ${unionName}`}
    >
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-muted-foreground">Union</span>
            <div className="font-medium">
              {fnum ? (
                <Link to={`/unions/${fnum}`} className="text-primary hover:underline">{unionName}</Link>
              ) : (
                unionName
              )}
            </div>
          </div>
          {affAbbr && (
            <div>
              <span className="text-muted-foreground">Affiliation</span>
              <div className="font-medium">{affAbbr}</div>
            </div>
          )}
          {unitSize != null && (
            <div>
              <span className="text-muted-foreground">Bargaining Unit Size</span>
              <div className="font-medium">{Number(unitSize).toLocaleString()}</div>
            </div>
          )}
          {noticeDate && (
            <div>
              <span className="text-muted-foreground">Latest Filing Date</span>
              <div className="font-medium">{new Date(noticeDate).toLocaleDateString()}</div>
            </div>
          )}
        </div>
        {fnum && (
          <Link to={`/unions/${fnum}`} className="text-sm text-primary hover:underline">
            View full union profile →
          </Link>
        )}
      </div>
    </CollapsibleCard>
  )
}
