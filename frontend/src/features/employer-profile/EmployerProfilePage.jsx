import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, useOutletContext } from 'react-router-dom'
import { ArrowLeft, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import { MiniStat } from '@/shared/components/MiniStat'
import { SidebarTOC } from '@/shared/components/SidebarTOC'
import { parseCanonicalId, useEmployerProfile, useEmployerUnifiedDetail, useScorecardDetail, useEmployerDataSources, useEmployerMatches, useEmployerOccupations, useEmployerFinancials } from '@/shared/api/profile'
import { useTargetDetail, useTargetScorecardDetail } from '@/shared/api/targets'
import { ProfileHeader } from './ProfileHeader'
import { ProfileActionButtons } from './ProfileActionButtons'
import { ScorecardSection } from './ScorecardSection'
import { SignalInventory } from './SignalInventory'
import { OshaSection } from './OshaSection'
import { EnvironmentalCard } from './EnvironmentalCard'
import { ExecutivesCard } from './ExecutivesCard'
import { InstitutionalOwnersCard } from './InstitutionalOwnersCard'
import { LobbyingCard } from './LobbyingCard'
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
import { CampaignOutcomeCard } from './CampaignOutcomeCard'
import { DataProvenanceCard } from './DataProvenanceCard'
import { ResearchInsightsCard } from './ResearchInsightsCard'
import { WorkforceDemographicsCard } from './WorkforceDemographicsCard'
import { NycEnforcementSection } from './NycEnforcementSection'
import { OccupationSection } from './OccupationSection'
import { FamilyRollupSection } from './FamilyRollupSection'

const PROFILE_SECTIONS = [
  { id: 'scorecard', label: 'Scorecard' },
  { id: 'provenance', label: 'Data Provenance' },
  { id: 'research', label: 'Research' },
  { id: 'union', label: 'Union' },
  { id: 'financial', label: 'Financial' },
  { id: 'demographics', label: 'Demographics' },
  { id: 'occupations', label: 'Occupations' },
  { id: 'corporate', label: 'Corporate' },
  { id: 'comparables', label: 'Comparables' },
  { id: 'family-rollup', label: 'Family Rollup' },
  { id: 'nlrb', label: 'NLRB' },
  { id: 'contracts', label: 'Contracts' },
  { id: 'osha', label: 'OSHA' },
  { id: 'whd', label: 'WHD' },
  { id: 'nyc', label: 'NYC Enforcement' },
  { id: 'crossrefs', label: 'Cross-Refs' },
  { id: 'notes', label: 'Notes' },
  { id: 'outcomes', label: 'Outcomes' },
]

function formatNumber(n) {
  if (n == null) return null
  return Number(n).toLocaleString()
}

function formatCurrency(n) {
  if (n == null) return null
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`
  return `$${Number(n).toLocaleString()}`
}

export function EmployerProfilePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { setBreadcrumbs } = useOutletContext() || {}
  const { isF7, sourceType, rawId } = parseCanonicalId(id)
  const isMaster = sourceType === 'MASTER'

  // IntersectionObserver state
  const [activeSection, setActiveSection] = useState('scorecard')
  const observerRef = useRef(null)

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

  // Occupation data — F7 only, after profile loads
  const occupationsQuery = useEmployerOccupations(isF7 ? id : null)

  // SEC/990 financials — F7 only, after profile loads
  const financialsQuery = useEmployerFinancials(id, { enabled: isF7 && !!data })

  // Master employer scorecard — must be called unconditionally (Rules of Hooks)
  const masterScorecardQuery = useTargetScorecardDetail(rawId, { enabled: isMaster && !!data })

  // Update page title with employer name when data loads
  const employerName = data?.employer?.employer_name || data?.display_name || data?.employer_name
  useEffect(() => {
    document.title = employerName
      ? `${employerName} - The Organizer`
      : 'Employer Profile - The Organizer'
  }, [employerName])

  // Set custom breadcrumbs with employer name
  useEffect(() => {
    if (setBreadcrumbs && employerName) {
      setBreadcrumbs([
        { label: 'Employers', to: '/search' },
        { label: employerName },
      ])
    }
  }, [setBreadcrumbs, employerName])

  // IntersectionObserver for sidebar TOC highlighting
  useEffect(() => {
    if (!isF7 || !data) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id)
          }
        }
      },
      { threshold: 0.2, rootMargin: '-80px 0px 0px 0px' }
    )
    observerRef.current = observer

    // Observe all section elements
    for (const section of PROFILE_SECTIONS) {
      const el = document.getElementById(section.id)
      if (el) observer.observe(el)
    }

    return () => observer.disconnect()
  }, [isF7, data])

  const handleBack = () => {
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

  // Master employer path — enriched view with signal inventory + family rollup
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
        {/* Corporate-family rollup -- aggregates NLRB/OSHA/WHD/F-7 across all
            name-variant siblings of this master. Self-gates on master_count > 5
            OR NLRB cases > 20, so single-location employers stay clean. */}
        <FamilyRollupSection masterId={rawId} />
        {/* 24Q-31: EPA ECHO environmental enforcement. Self-fetches via
            useMasterEpaEcho. Closes Q21 Environmental on the master path. */}
        <EnvironmentalCard masterId={rawId} />
        {/* 24Q-7: Mergent executive roster. Self-fetches via
            useMasterExecutives. Moves Q8 Management Medium -> Strong. */}
        <ExecutivesCard masterId={rawId} />
        {/* 24Q-9: SEC Form 13F institutional owners. Self-fetches via
            useMasterInstitutionalOwners. Moves Q9 Stockholders Missing
            -> Strong for publicly-traded targets. */}
        <InstitutionalOwnersCard masterId={rawId} />
        {/* 24Q-39: LDA federal lobbying. Self-fetches via
            useMasterLobbying. One pillar of Q24 Political alongside
            FEC contributions. */}
        <LobbyingCard masterId={rawId} />
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
  const matchSummary = matchesQuery.data?.match_summary

  function getAttribution(sourceSystem) {
    if (!matchSummary) return null
    return matchSummary.find(e => e.source_system === sourceSystem) || null
  }

  function getFinancialAttribution() {
    if (!matchSummary) return null
    const s990 = matchSummary.find(e => e.source_system === '990')
    const sec = matchSummary.find(e => e.source_system === 'sec')
    if (!s990 && !sec) return null
    if (!s990) return sec
    if (!sec) return s990
    const s990Score = s990.best_confidence_score ?? s990.best_confidence ?? 0
    const secScore = sec.best_confidence_score ?? sec.best_confidence ?? 0
    return secScore > s990Score ? sec : s990
  }

  function getCorporateAttribution() {
    if (!matchSummary) return null
    const candidates = ['sec', 'corpwatch', 'mergent']
    const entries = candidates.map(s => matchSummary.find(e => e.source_system === s)).filter(Boolean)
    if (entries.length === 0) return null
    return entries.reduce((best, e) => {
      const bestScore = best.best_confidence_score ?? best.best_confidence ?? 0
      const eScore = e.best_confidence_score ?? e.best_confidence ?? 0
      return eScore > bestScore ? e : best
    })
  }

  // Build summary parts for hero banner
  const summaryParts = []
  if (osha?.summary?.total_violations) summaryParts.push(`${formatNumber(osha.summary.total_violations)} OSHA violations`)
  if (scorecard?.score_whd != null) summaryParts.push('Wage theft cases on file')
  const ds = dataSourcesQuery.data
  if (ds?.is_federal_contractor && ds?.federal_obligations) {
    summaryParts.push(`${formatCurrency(ds.federal_obligations)} federal contracts`)
  }
  if (!employer.union_name && !employer.latest_union_name) {
    summaryParts.push('Non-union')
  }

  // Filter sidebar sections to only show ones with data
  const visibleSections = PROFILE_SECTIONS.filter(s => {
    switch (s.id) {
      case 'scorecard': return !!scorecard
      case 'provenance': return !!matchesQuery.data?.match_summary?.length
      case 'research': return !!scorecardQuery.data?.has_research
      case 'union': return !!(employer.union_name || employer.latest_union_name)
      case 'financial': return !!(scorecard?.score_financial != null || scorecard?.bls_growth_pct != null || ds?.is_public)
      case 'demographics': return !!(employer?.state && (scorecard?.naics || employer?.naics))
      case 'occupations': return !!(occupationsQuery.data?.top_occupations?.length)
      case 'corporate': return true  // fetches its own data
      case 'comparables': return true  // fetches its own data
      case 'nlrb': return true  // shows warning when no data
      case 'contracts': return !!(ds?.is_federal_contractor)
      case 'osha': return true  // shows warning when no data
      case 'whd': return true  // shows warning when no data
      case 'nyc': return true  // shows warning when no data
      case 'crossrefs': return !!(crossRefs?.length)
      case 'notes': return true  // always show
      case 'outcomes': return true
      default: return true
    }
  })

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
        <ArrowLeft className="h-4 w-4" />
        Back
      </Button>

      {/* Hero banner - full width */}
      <ProfileHeader
        employer={employer}
        scorecard={scorecard}
        sourceType="F7"
        isUnionReference={data.is_union_reference === true}
        summaryParts={summaryParts}
        dataSources={ds}
        entityContext={data?.entity_context}
      />

      {/* MiniStat row - full width */}
      <div className="flex gap-3 flex-wrap">
        <MiniStat
          label="WORKERS"
          value={(() => {
            const ec = data?.entity_context
            // family_primary: show the range when SEC + Mergent agree, else the
            // primary count. Respects the API's range-vs-flag decision so the
            // hero MiniStat stays consistent with the EntityContextBlock below.
            if (ec?.display_mode === 'family_primary' && ec.family?.primary_count != null) {
              if (ec.family.range?.display) return ec.family.range.display
              return formatNumber(ec.family.primary_count)
            }
            if (ec?.unit?.count != null) return formatNumber(ec.unit.count)
            return formatNumber(employer.consolidated_workers || employer.unit_size || employer.total_workers)
          })()}
          sub={
            data?.entity_context?.display_mode === 'family_primary'
              ? 'Corp. family'
              : data?.entity_context?.unit?.count != null
              ? 'This unit'
              : undefined
          }
          accent="#1a6b5a"
        />
        <MiniStat
          label="OSHA VIOLATIONS"
          value={osha?.summary?.total_violations != null ? formatNumber(osha.summary.total_violations) : '--'}
          sub={osha?.summary?.serious_violations ? `${osha.summary.serious_violations} serious` : undefined}
          accent="#c23a22"
        />
        {scorecard?.score_whd != null && (
          <MiniStat
            label="WAGE CASES"
            value={scorecard.score_whd > 0 ? 'Yes' : '--'}
            sub={scorecard.whd_backwages ? formatCurrency(scorecard.whd_backwages) : undefined}
            accent="#c78c4e"
          />
        )}
        {ds?.is_federal_contractor && (
          <MiniStat
            label="FED CONTRACTS"
            value={ds.federal_obligations ? formatCurrency(ds.federal_obligations) : '--'}
            sub={ds.federal_contract_count ? `${ds.federal_contract_count} contracts` : undefined}
            accent="#4a90a4"
          />
        )}
      </div>

      {/* Two-column: sidebar + main */}
      <div className="flex gap-6">
        <SidebarTOC sections={visibleSections} activeSection={activeSection} />
        <div className="flex-1 min-w-0 space-y-4">
          <div id="scorecard">
            <ScorecardSection scorecard={scorecard} explanations={explanations} scorecardDetail={scorecardQuery.data} matchSummary={matchSummary} />
          </div>
          <div id="provenance">
            <DataProvenanceCard matchSummary={matchesQuery.data?.match_summary} />
          </div>
          <div id="research">
            <ResearchInsightsCard scorecard={scorecardQuery.data} />
          </div>
          <div id="union">
            <UnionRelationshipsCard employer={employer} />
          </div>
          <div id="financial">
            <FinancialDataCard scorecard={scorecard} dataSources={dataSourcesQuery.data} financials={financialsQuery.data} sourceAttribution={getFinancialAttribution()} />
          </div>
          <div id="demographics">
            <WorkforceDemographicsCard state={employer?.state} naics={scorecard?.naics || employer?.naics} employerId={id} />
          </div>
          <div id="occupations">
            <OccupationSection data={occupationsQuery.data} isLoading={occupationsQuery.isLoading} />
          </div>
          <div id="corporate">
            <CorporateHierarchyCard employerId={id} sourceAttribution={getCorporateAttribution()} />
          </div>
          <div id="comparables">
            <ComparablesCard employerId={id} />
          </div>
          {/* Corporate-family rollup for F-7 profiles: resolves the F-7's
              name_standard to the same canonical stem the master variant uses,
              so a per-store Starbucks F-7 profile sees the full 2,351-case
              national rollup. Self-gates on master_count > 5 OR NLRB > 20. */}
          {isF7 && (
            <div id="family-rollup">
              <FamilyRollupSection f7Id={id} />
            </div>
          )}
          <div id="nlrb">
            <NlrbSection nlrb={nlrb} sourceAttribution={getAttribution('nlrb')} scorecard={scorecard} dataSources={ds} docket={data?.nlrb_docket} />
          </div>
          <div id="contracts">
            <GovernmentContractsCard dataSources={dataSourcesQuery.data} sourceAttribution={getAttribution('sam')} />
          </div>
          <div id="osha">
            <OshaSection osha={osha} sourceAttribution={getAttribution('osha')} dataSources={ds} />
          </div>
          <div id="whd">
            <WhdCard employerId={id} sourceAttribution={getAttribution('whd')} dataSources={ds} />
          </div>
          <div id="nyc">
            <NycEnforcementSection nycEnforcement={data.nyc_enforcement} />
          </div>
          <div id="crossrefs">
            <CrossReferencesSection crossReferences={crossRefs} />
          </div>
          <div id="notes">
            <ResearchNotesCard employerId={id} sourceType="F7" sourceId={employer.employer_id} />
          </div>
          <div id="outcomes">
            <CampaignOutcomeCard employerId={id} employerName={employer.employer_name} />
          </div>

          {/* Action buttons at bottom */}
          <div className="flex gap-3 mt-6 pt-6 border-t border-[#d9cebb]">
            <ProfileActionButtons employer={employer} scorecard={scorecard} entityContext={data?.entity_context} />
          </div>
        </div>
      </div>
    </div>
  )
}
