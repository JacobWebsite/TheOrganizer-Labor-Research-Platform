import { useQuery } from '@tanstack/react-query'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { apiClient } from '@/shared/api/client'

function StatBar({ label, pct, color = 'bg-[#8B6914]' }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-40 text-[#3D2B1F]/70 truncate" title={label}>{label}</span>
      <div className="flex-1 bg-[#E8DCC8] rounded h-4 overflow-hidden">
        <div
          className={`${color} h-full rounded transition-all`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <span className="w-12 text-right font-medium text-[#3D2B1F]">{pct}%</span>
    </div>
  )
}

function DemographicSection({ title, items }) {
  if (!items || items.length === 0) return null
  return (
    <div>
      <h4 className="text-sm font-semibold text-[#3D2B1F] mb-2 uppercase tracking-wide">{title}</h4>
      <div className="space-y-1.5">
        {items.map((item, i) => (
          <StatBar key={i} label={item.label || item.group || item.bucket} pct={item.pct} />
        ))}
      </div>
    </div>
  )
}

export function WorkforceDemographicsCard({ state, naics }) {
  const enabled = !!state && !!naics
  const path = naics
    ? `/api/demographics/${state}/${naics}`
    : `/api/demographics/${state}`

  const { data, isLoading, isError } = useQuery({
    queryKey: ['demographics', state, naics],
    queryFn: () => apiClient.get(path),
    enabled,
    staleTime: 1000 * 60 * 30, // cache 30 min
  })

  if (!enabled) return null
  if (isLoading) return (
    <CollapsibleCard title="Workforce Demographics" defaultOpen={false}>
      <p className="text-sm text-[#3D2B1F]/50 italic">Loading demographics...</p>
    </CollapsibleCard>
  )
  if (isError || !data) return null

  return (
    <CollapsibleCard title="Workforce Demographics" defaultOpen={false}>
      <p className="text-xs text-[#3D2B1F]/60 mb-4 italic">
        {data.label} -- {data.total_workers?.toLocaleString()} estimated workers (ACS)
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <DemographicSection title="Gender" items={data.gender} />
        <DemographicSection title="Age Distribution" items={data.age_distribution} />
        <DemographicSection title="Race/Ethnicity" items={data.race} />
        <DemographicSection title="Education" items={data.education} />
        {data.hispanic && data.hispanic.length > 0 && (
          <DemographicSection title="Hispanic/Latino Origin" items={data.hispanic} />
        )}
      </div>
    </CollapsibleCard>
  )
}
