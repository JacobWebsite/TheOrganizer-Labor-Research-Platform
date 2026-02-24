import { useEffect } from 'react'
import { Settings, ShieldAlert } from 'lucide-react'
import { useAuthStore } from '@/shared/stores/authStore'
import { HelpSection } from '@/shared/components/HelpSection'
import { HealthStatusCard } from './HealthStatusCard'
import { PlatformStatsCard } from './PlatformStatsCard'
import { DataFreshnessCard } from './DataFreshnessCard'
import { MatchQualityCard } from './MatchQualityCard'
import { MatchReviewCard } from './MatchReviewCard'
import { RefreshActionsCard } from './RefreshActionsCard'
import { UserRegistrationCard } from './UserRegistrationCard'

export function SettingsPage() {
  const user = useAuthStore((s) => s.user)

  useEffect(() => { document.title = 'Administration - The Organizer' }, [])

  if (!user || user.role !== 'admin') {
    return (
      <div className='flex flex-col items-center justify-center py-20'>
        <ShieldAlert className='h-12 w-12 text-muted-foreground mb-4' />
        <h2 className='text-xl font-semibold mb-2'>Access Denied</h2>
        <p className='text-muted-foreground'>You need admin privileges to view this page.</p>
      </div>
    )
  }

  return (
    <div className='space-y-6'>
      <div className='flex items-center gap-2'>
        <Settings className='h-6 w-6 text-primary' />
        <h1 className='text-2xl font-bold'>Administration</h1>
      </div>
      <HelpSection>
        <p><strong>This page is only visible to administrators.</strong></p>
        <p><strong>Data freshness:</strong> Shows when each data source was last updated. Government databases are updated on different schedules -- some monthly, some quarterly, some annually. Stale data (more than 6 months old) is highlighted. Refresh buttons trigger a new data pull from the source.</p>
        <p><strong>Match review queue:</strong> When users click "Report a problem" on an employer profile, it appears here. Each item shows which employer and which data source the user flagged, along with the current match confidence. Admins can approve the match (dismiss the flag) or reject it (unlink the data source from that employer).</p>
        <p><strong>System health:</strong> Database size, API response times (slower than 2 seconds may indicate a problem), and error rates (should be near zero).</p>
        <p><strong>User management:</strong> Add, remove, or change roles for platform users.</p>
        <ul className='list-disc pl-5 space-y-1 text-sm'>
          <li><strong>Viewer:</strong> Can search and view everything but cannot flag, export, or report problems.</li>
          <li><strong>Researcher:</strong> Can flag employers, export CSVs, and report bad matches.</li>
          <li><strong>Admin:</strong> Full access including this admin panel, score weights, and user management.</li>
        </ul>
      </HelpSection>
      <div className='grid grid-cols-1 gap-6 md:grid-cols-2'>
        <HealthStatusCard />
        <PlatformStatsCard />
      </div>
      <DataFreshnessCard />
      <MatchQualityCard />
      <MatchReviewCard />
      <div className='grid grid-cols-1 gap-6 md:grid-cols-2'>
        <RefreshActionsCard />
        <UserRegistrationCard />
      </div>
    </div>
  )
}
