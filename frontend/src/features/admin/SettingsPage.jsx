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
        <p><strong>System Health:</strong> Green dots indicate services are running normally. Red means something needs attention.</p>
        <p><strong>Data Freshness:</strong> Shows when each data source was last updated. Stale data (highlighted red) may need a refresh.</p>
        <p><strong>Match Review:</strong> Review matches flagged for quality. Approve correct matches or reject incorrect ones.</p>
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
