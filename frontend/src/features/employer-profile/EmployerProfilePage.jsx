import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import { HelpSection } from '@/shared/components/HelpSection'
import { parseCanonicalId, useEmployerProfile, useEmployerUnifiedDetail, useScorecardDetail, useEmployerDataSources, useEmployerMatches } from '@/shared/api/profile'
import { useTargetDetail, useTargetScorecardDetail } from '@/shared/api/targets'
import { ProfileHeader } from './ProfileHeader'
import { ScorecardSection } from './ScorecardSection'
import { SignalInventory } from './SignalInventory'
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
import { DataProvenanceCard } from './DataProvenanceCard'

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
  const matchesQuery = useEmployerMatches(id, { enabled: isF7 && !!data })

  // Update page title with employer name when data loads
  const employerName = data?.employer?.employer_name || data?.display_name || data?.employer_name
  useEffect(() => {
    document.title = employerName
      ? `${employerName} - The Organizer`
      : 'Employer Profile - The Organizer'
  }, [employerName])

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

  // Master employer path — enriched view with signal inventory
  const masterScorecardQuery = useTargetScorecardDetail(rawId, { enabled: isMaster && !!data })

  if (isMaster && data) {
    const masterEmployer = data.master || data
    const masterScorecard = masterScorecardQuery.data?.scorecard
    const masterSignals = masterScorecardQuery.data?.signals

    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <ProfileHeader
          employer={masterEmployer}
          sourceType="MASTER"
          isUnionReference={false}
          targetSignals={masterScorecard}
        />
        <SignalInventory scorecard={masterScorecard} signals={masterSignals} />
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

      <ProfileHeader
        employer={employer}
        scorecard={scorecard}
        sourceType="F7"
        isUnionReference={data.is_union_reference === true}
      />
      <HelpSection>
        <p><strong>Score (0-10):</strong> This employer's overall organizing potential, calculated from up to 8 different factors. The score only uses factors where we actually have data -- if we're missing information on a factor, it's skipped rather than counted against the employer. A score of 8.0 based on 7 factors is more reliable than an 8.0 based on 3 factors. The number of factors used is shown below the score.</p>
        <p><strong>Tiers -- what they mean and what to do with them:</strong></p>
        <ul className="list-disc pl-5 space-y-1 text-sm">
          <li><strong>Priority (top 3%):</strong> The strongest organizing targets in the entire database. Multiple strong signals across strategic position, leverage, and worker conditions. Action: prioritize for active campaign planning and resource allocation.</li>
          <li><strong>Strong (next 12%):</strong> Very promising targets with solid data across several factors. Action: worth detailed research and preliminary outreach assessment.</li>
          <li><strong>Promising (next 25%):</strong> Good potential but may be missing data or have mixed signals. Action: monitor and investigate further.</li>
          <li><strong>Moderate (next 35%):</strong> Some positive signals but not enough to stand out. Action: keep on the radar but don't prioritize over higher-tier targets.</li>
          <li><strong>Low (bottom 25%):</strong> Few organizing signals in the available data. Action: unlikely to be a strong target based on current information, but new data could change this.</li>
        </ul>
        <p><strong>Factor bars:</strong> Each bar shows how this employer scored on one of 8 factors, rated 0-10. Factors are weighted by importance -- (3x) factors matter three times as much as (1x) factors in the final score. A grayed-out factor with a dash means we have no data for that factor.</p>
        <ul className="list-disc pl-5 space-y-1 text-sm">
          <li><strong>Union Proximity (3x):</strong> Whether companies in the same corporate family already have unions. Strongest predictor -- the corporate parent has already dealt with unions elsewhere.</li>
          <li><strong>Employer Size (filter):</strong> Shown for context but not weighted in the score. Use it to filter searches by workforce size rather than as a ranking signal.</li>
          <li><strong>NLRB Activity (3x):</strong> This employer's own NLRB election history and ULP complaints, plus organizing momentum in their industry and state. Recent activity counts more.</li>
          <li><strong>Gov Contracts (2x):</strong> Federal government contracts (USASpending/SAM.gov) create public accountability and regulatory leverage. Higher contract obligations score higher. State/local contracts not yet included.</li>
          <li><strong>Industry Growth (2x):</strong> BLS-projected 10-year industry growth rate. Faster-growing industries mean more workers entering the field.</li>
          <li><strong>OSHA Safety (1x):</strong> Workplace safety violations. More violations and more serious violations (willful, repeat) score higher. Recent ones count more.</li>
          <li><strong>WHD Wage Theft (1x):</strong> Wage and hour violations including back wages, overtime, and minimum wage violations.</li>
          <li><strong>Financial (2x):</strong> Revenue scale, asset cushion, and revenue-per-worker from 990 filings or SEC data.</li>
        </ul>
        <p><strong>Source badges -- what each database is:</strong></p>
        <ul className="list-disc pl-5 space-y-1 text-sm">
          <li><strong>F-7:</strong> DOL Form LM-10/F-7 filings. Employers with union contracts are required to file these.</li>
          <li><strong>OSHA:</strong> Occupational Safety and Health Administration inspection records.</li>
          <li><strong>NLRB:</strong> National Labor Relations Board case records -- election petitions, results, and unfair labor practice complaints.</li>
          <li><strong>WHD:</strong> Wage and Hour Division enforcement records -- wage theft, overtime, minimum wage investigations.</li>
          <li><strong>SAM:</strong> System for Award Management -- federal government contractor database.</li>
          <li><strong>SEC:</strong> Securities and Exchange Commission filings -- public company data from EDGAR.</li>
        </ul>
        <p><strong>Confidence dots:</strong> How confident the system is that records from a data source were correctly matched to this employer. 4 dots = matched on unique ID (EIN or exact name + address). 3 dots = name + state or city. 2 dots = fuzzy name similarity + location. 1 dot = name similarity alone -- treat with caution.</p>
        <p><strong>Employee count range:</strong> Different databases collect employee counts at different times using different definitions. The platform shows the range across all sources so you can see the spread. The scoring system uses the average.</p>
      </HelpSection>
      <ScorecardSection scorecard={scorecard} explanations={explanations} />
      <DataProvenanceCard matchSummary={matchesQuery.data?.match_summary} />
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
