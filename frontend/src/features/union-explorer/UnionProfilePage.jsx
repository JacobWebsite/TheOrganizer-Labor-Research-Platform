import { useEffect } from 'react'
import { useParams, useOutletContext } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import {
  useUnionDetail,
  useUnionMembershipHistory,
  useUnionOrganizingCapacity,
  useUnionEmployers,
  useUnionDisbursements,
  useUnionHealth,
} from '@/shared/api/unions'
import { UnionProfileHeader } from './UnionProfileHeader'
import { UnionWebProfileSection } from './UnionWebProfileSection'
import { MembershipSection } from './MembershipSection'
import { OrganizingCapacitySection } from './OrganizingCapacitySection'
import { UnionEmployersTable } from './UnionEmployersTable'
import { UnionElectionsSection } from './UnionElectionsSection'
import { UnionFinancialsSection } from './UnionFinancialsSection'
import { UnionAssetsSection } from './UnionAssetsSection'
import { UnionDisbursementsSection } from './UnionDisbursementsSection'
import { SisterLocalsSection } from './SisterLocalsSection'
import { ExpansionTargetsSection } from './ExpansionTargetsSection'
import { UnionHealthSection } from './UnionHealthSection'

export function UnionProfilePage() {
  const { fnum } = useParams()
  const { setBreadcrumbs } = useOutletContext() || {}

  const detailQuery = useUnionDetail(fnum)
  const membershipQuery = useUnionMembershipHistory(fnum)
  const capacityQuery = useUnionOrganizingCapacity(fnum)
  const employersQuery = useUnionEmployers(fnum)
  const disbursementsQuery = useUnionDisbursements(fnum)
  const healthQuery = useUnionHealth(fnum)

  const { data: detail, isLoading, isError, error } = detailQuery

  // Set custom breadcrumbs with union name and affiliation
  // (must be called before any early returns to satisfy rules of hooks)
  const unionName = detail?.union?.abbreviation || detail?.union?.union_name
  const affiliation = detail?.union?.affiliation
  useEffect(() => {
    if (setBreadcrumbs && unionName) {
      const crumbs = [{ label: 'Unions', to: '/unions' }]
      if (affiliation) crumbs.push({ label: affiliation, to: '/unions' })
      crumbs.push({ label: unionName })
      setBreadcrumbs(crumbs)
    }
  }, [setBreadcrumbs, unionName, affiliation])

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-4">
        <PageSkeleton variant="union-profile" />
      </div>
    )
  }

  // 404 error
  if (isError && error?.status === 404) {
    return (
      <div className="space-y-4">
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <AlertTriangle className="h-12 w-12 text-muted-foreground mb-4" />
          <h2 className="text-xl font-semibold mb-1">Union not found</h2>
          <p className="text-sm text-muted-foreground">
            No union with F-Num "{fnum}" exists in the database.
          </p>
        </div>
      </div>
    )
  }

  // Generic error
  if (isError) {
    return (
      <div className="space-y-4">
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
          <h2 className="text-xl font-semibold mb-1">Something went wrong</h2>
          <p className="text-sm text-muted-foreground">
            {error?.message || 'Failed to load union profile.'}
          </p>
        </div>
      </div>
    )
  }

  if (!detail) return null

  const union = detail.union || {}
  const nlrbElections = detail.nlrb_elections || null
  const nlrbSummary = detail.nlrb_summary || null
  // Compose elections prop: pass through source/note/affiliation metadata with the list
  // so <UnionElectionsSection> can render the affiliate notice. Accepts either a flat
  // array (new backend shape) or the legacy object-with-elections shape.
  const electionsProp = Array.isArray(nlrbElections)
    ? {
        list: nlrbElections,
        elections_source: detail.elections_source || null,
        election_note: detail.election_note || null,
        affiliation: union.aff_abbr || union.affiliation || null,
      }
    : nlrbElections
  const financialTrends = detail.financial_trends || []
  const sisterLocals = detail.sister_locals || []

  // Use full employers list if available, fallback to detail top_employers
  const employers = employersQuery.data?.employers || detail.top_employers || []

  return (
    <div className="space-y-4">
      {union.is_likely_inactive && (
        <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-300 rounded-lg text-sm text-amber-800">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>Likely Inactive -- Last filing year: {union.yr_covered || 'Unknown'}</span>
        </div>
      )}
      <UnionProfileHeader union={union} employers={employers} healthGrade={healthQuery.data?.composite?.grade} />
      <UnionWebProfileSection webProfile={detail.web_profile} />
      <UnionHealthSection data={healthQuery.data} isLoading={healthQuery.isLoading} />
      <MembershipSection data={membershipQuery.data} />
      <OrganizingCapacitySection data={capacityQuery.data} />
      <UnionEmployersTable employers={employers} />
      <UnionElectionsSection elections={electionsProp} summary={nlrbSummary} />
      <UnionFinancialsSection trends={financialTrends} />
      <UnionAssetsSection fileNumber={fnum} />
      <UnionDisbursementsSection data={disbursementsQuery.data} isLoading={disbursementsQuery.isLoading} />
      <SisterLocalsSection sisters={sisterLocals} />
      <ExpansionTargetsSection union={union} employers={employers} />
    </div>
  )
}
