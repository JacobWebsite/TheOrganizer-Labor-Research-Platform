import { useParams } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import {
  useUnionDetail,
  useUnionMembershipHistory,
  useUnionOrganizingCapacity,
  useUnionEmployers,
} from '@/shared/api/unions'
import { UnionProfileHeader } from './UnionProfileHeader'
import { MembershipSection } from './MembershipSection'
import { OrganizingCapacitySection } from './OrganizingCapacitySection'
import { UnionEmployersTable } from './UnionEmployersTable'
import { UnionElectionsSection } from './UnionElectionsSection'
import { UnionFinancialsSection } from './UnionFinancialsSection'
import { SisterLocalsSection } from './SisterLocalsSection'
import { ExpansionTargetsSection } from './ExpansionTargetsSection'

export function UnionProfilePage() {
  const { fnum } = useParams()

  const detailQuery = useUnionDetail(fnum)
  const membershipQuery = useUnionMembershipHistory(fnum)
  const capacityQuery = useUnionOrganizingCapacity(fnum)
  const employersQuery = useUnionEmployers(fnum)

  const { data: detail, isLoading, isError, error } = detailQuery

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
  const financialTrends = detail.financial_trends || []
  const sisterLocals = detail.sister_locals || []

  // Use full employers list if available, fallback to detail top_employers
  const employers = employersQuery.data?.employers || detail.top_employers || []

  return (
    <div className="space-y-4">
      <UnionProfileHeader union={union} employers={employers} />
      <MembershipSection data={membershipQuery.data} />
      <OrganizingCapacitySection data={capacityQuery.data} />
      <UnionEmployersTable employers={employers} />
      <UnionElectionsSection elections={nlrbElections} />
      <UnionFinancialsSection trends={financialTrends} />
      <SisterLocalsSection sisters={sisterLocals} />
      <ExpansionTargetsSection union={union} employers={employers} />
    </div>
  )
}
