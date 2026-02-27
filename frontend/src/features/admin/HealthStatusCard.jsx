import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useSystemHealth } from '@/shared/api/admin'

function StatusDot({ ok }) {
  return (
    <span
      className={`inline-block h-3 w-3 rounded-full ${ok ? 'bg-[#3a7d44]' : 'bg-[#c23a22]'}`}
    />
  )
}

function StatusRow({ label, ok }) {
  return (
    <div className='flex items-center justify-between py-2'>
      <span className='text-sm font-medium'>{label}</span>
      <div className='flex items-center gap-2'>
        <StatusDot ok={ok} />
        <span className='text-sm text-muted-foreground'>
          {ok ? 'Healthy' : 'Down'}
        </span>
      </div>
    </div>
  )
}

export function HealthStatusCard() {
  const { data, isLoading } = useSystemHealth()

  return (
    <Card>
      <CardHeader>
        <CardTitle>System Health</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className='space-y-3'>
            <Skeleton className='h-5 w-full' />
            <Skeleton className='h-5 w-full' />
          </div>
        ) : (
          <div className='divide-y'>
            <StatusRow label='API' ok={data?.status === 'ok'} />
            <StatusRow label='Database' ok={data?.db === true || data?.database === 'ok'} />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
