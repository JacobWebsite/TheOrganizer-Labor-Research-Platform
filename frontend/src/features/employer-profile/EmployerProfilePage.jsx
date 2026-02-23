import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import { HelpSection } from '@/shared/components/HelpSection'
import { parseCanonicalId, useEmployerProfile, useEmployerUnifiedDetail, useScorecardDetail, useEmployerDataSources } from '@/shared/api/profile'
import { useTargetDetail } from '@/shared/api/targets'
import { ProfileHeader } from './ProfileHeader'
import { ScorecardSection } from './ScorecardSection'
import { OshaSection } from './OshaSection'
import { NlrbSection } from './NlrbSection'
import { CrossReferencesSection } from './CrossReferencesSection'
import { BasicProfileView } from './BasicProfileView'
import { UnionRelationshipsCard } from './UnionRelationshipsCard'
import { FinancialDataCard } from './FinancialDataCard'
import { CorporateHierarchyCard } from './CorporateHierarchyCard'
import { ComparablesCard } from './ComparablesCard'
import { GovernmentContractsCard } from './GovernmentContractsCard'
import { WhdCard } from './WhdCard'
import { ResearchNotesCard } from './ResearchNotesCard'

export function EmployerProfilePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { isF7, sourceType, rawId } = parseCanonicalId(id)
  const isMaster = sourceType === 'MASTER'

  // Mutually exclusive — only one fires per page load
  const f7Query = useEmployerProfile(id, { enabled: isF7 })
  const nonF7Query = useEmployerUnifiedDetail(id, { enabled: !isF7 && !isMaster })
  const masterQuery = useTargetDetail(rawId, { enabled: isMaster })

  const activeQuery = isMaster ? masterQuery : isF7 ? f7Query : nonF7Query
  const { data, isLoading, isError, error } = activeQuery

  // Scorecard detail (explanations) — only for F7, after profile loads
  const scorecardQuery = useScorecardDetail(id, { enabled: isF7 && !!data })
  const dataSourcesQuery = useEmployerDataSources(id, { enabled: isF7 && !!data })

  const handleBack = () => {
    // Try to go back in history; if no history, go to search
    if (window.history.length > 1) {
      navigate(-1)
    } else {
      navigate('/search')
    }
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <PageSkeleton variant="profile" />
      </div>
    )
  }

  // 404 error
  if (isError && error?.status === 404) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <AlertTriangle className="h-12 w-12 text-muted-foreground mb-4" />
          <h2 className="text-xl font-semibold mb-1">Employer not found</h2>
          <p className="text-sm text-muted-foreground">
            No employer with ID "{id}" exists in the database.
          </p>
        </div>
      </div>
    )
  }

  // Generic error
  if (isError) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
          <h2 className="text-xl font-semibold mb-1">Something went wrong</h2>
          <p className="text-sm text-muted-foreground mb-4">
            {error?.message || 'Failed to load employer profile.'}
          </p>
          <Button variant="outline" size="sm" onClick={() => activeQuery.refetch()}>
            Retry
          </Button>
        </div>
      </div>
    )
  }

  // Master employer path — enriched basic view
  if (isMaster && data) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <BasicProfileView data={data} isMaster />
      </div>
    )
  }

  // Non-F7 path — basic view
  if (!isF7 && data) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <BasicProfileView data={data} />
      </div>
    )
  }

  // F7 path — full rich view
  if (!data) return null

  const employer = data.employer || {}
  const scorecard = data.unified_scorecard || {}
  const osha = data.osha
  const nlrb = data.nlrb
  const crossRefs = data.cross_references
  const explanations = scorecardQuery.data?.explanations

  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
        <ArrowLeft className="h-4 w-4" />
        Back
      </Button>

      <ProfileHeader employer={employer} scorecard={scorecard} sourceType="F7" />
      <HelpSection>
        <p><strong>Score (0-10):</strong> This employer's overall organizing potential, calculated from up to 8 different factors. If a factor has no data, it's skipped rather than counted against the employer.</p>
        <p><strong>Factor bars:</strong> Each bar shows how this employer scored on one factor, rated 0-10. Factors weighted (3x) matter three times as much as (1x) factors. A grayed-out bar with a dash means no data.</p>
        <p><strong>Source badges:</strong> Which government databases have records for this employer. More badges generally means more complete data.</p>
        <p><strong>Confidence dots:</strong> How confident the system is that records were correctly matched to this employer. 4 dots = matched on unique ID. 1 dot = fuzzy name match only.</p>
      </HelpSection>
      <ScorecardSection scorecard={scorecard} explanations={explanations} />
      <UnionRelationshipsCard employer={employer} />
      <FinancialDataCard scorecard={scorecard} dataSources={dataSourcesQuery.data} />
      <CorporateHierarchyCard employerId={id} />
      <ComparablesCard employerId={id} />
      <NlrbSection nlrb={nlrb} />
      <GovernmentContractsCard dataSources={dataSourcesQuery.data} />
      <OshaSection osha={osha} />
      <WhdCard employerId={id} />
      <CrossReferencesSection crossReferences={crossRefs} />
      <ResearchNotesCard employerId={id} sourceType="F7" sourceId={employer.employer_id} />
    </div>
  )
}
