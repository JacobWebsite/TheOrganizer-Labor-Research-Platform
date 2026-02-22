import { Info } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { ProfileHeader } from './ProfileHeader'
import { CrossReferencesSection } from './CrossReferencesSection'

export function BasicProfileView({ data }) {
  if (!data) return null

  const employer = data.employer || {}
  const sourceType = data.source_type || 'UNKNOWN'

  return (
    <div className="space-y-4">
      <ProfileHeader employer={employer} sourceType={sourceType} />

      <Card>
        <CardContent className="p-4">
          <div className="flex items-start gap-2 text-sm text-muted-foreground">
            <Info className="h-4 w-4 mt-0.5 shrink-0" />
            <p>
              This employer was found via {sourceType} records. Limited data is available.
              Scorecard, OSHA, and detailed NLRB data are only available for employers in LM filing records (F7).
            </p>
          </div>
        </CardContent>
      </Card>

      <CrossReferencesSection crossReferences={data.cross_references} />
    </div>
  )
}
