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

function DataSourceBadge({ label, available }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium mr-1 mb-1 ${
      available ? 'bg-[#8B6914]/15 text-[#8B6914]' : 'bg-[#E8DCC8]/50 text-[#3D2B1F]/30'
    }`}>
      {label}
    </span>
  )
}

function MetricBox({ label, value, sub }) {
  if (value == null) return null
  return (
    <div className="bg-[#F5F0E8] rounded px-3 py-2 text-center">
      <div className="text-lg font-bold text-[#3D2B1F]">{value}</div>
      <div className="text-xs text-[#3D2B1F]/60">{label}</div>
      {sub && <div className="text-xs text-[#3D2B1F]/40 mt-0.5">{sub}</div>}
    </div>
  )
}

function IndustryContextSection({ data }) {
  const { qcew, soii, jolts, union_density, ncs } = data

  const hasContext = qcew || soii || jolts || union_density || ncs
  if (!hasContext) return null

  return (
    <div className="mt-6 pt-4 border-t border-[#d9cebb]">
      <h3 className="text-sm font-bold text-[#3D2B1F] mb-3 uppercase tracking-wider">
        Industry & Local Context
      </h3>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 mb-4">
        {qcew && (
          <>
            <MetricBox
              label="Local Employment"
              value={qcew.local_employment?.toLocaleString()}
              sub={`${qcew.local_establishments?.toLocaleString() || '?'} establishments`}
            />
            <MetricBox
              label="Avg Annual Pay"
              value={qcew.avg_annual_pay ? `$${Math.round(qcew.avg_annual_pay).toLocaleString()}` : null}
              sub={`QCEW ${qcew.year}`}
            />
          </>
        )}

        {soii && (
          <MetricBox
            label="Injury Rate"
            value={soii.total_recordable_rate}
            sub={`per 100 workers (${soii.year})`}
          />
        )}

        {union_density?.state && (
          <MetricBox
            label="Union Density (State)"
            value={`${union_density.state.union_density_pct}%`}
            sub={`CPS ${union_density.state.year}`}
          />
        )}

        {union_density?.industry && (
          <MetricBox
            label="Union Density (Industry)"
            value={`${union_density.industry.union_density_pct}%`}
            sub={union_density.industry.industry_name}
          />
        )}

        {union_density?.state_industry && (
          <MetricBox
            label="Union Density (Est.)"
            value={`${union_density.state_industry.estimated_density_pct}%`}
            sub={`${union_density.state_industry.confidence} confidence`}
          />
        )}
      </div>

      {jolts && Object.keys(jolts.rates).length > 0 && (
        <div className="mb-3">
          <h4 className="text-xs font-semibold text-[#3D2B1F]/70 mb-2 uppercase">
            Turnover Rates (JOLTS {jolts.year})
          </h4>
          <div className="flex flex-wrap gap-3">
            {Object.entries(jolts.rates).map(([key, rate]) => (
              <span key={key} className="text-xs text-[#3D2B1F]/70">
                <span className="font-medium">{key}:</span> {rate}%
              </span>
            ))}
          </div>
        </div>
      )}

      {ncs && Object.keys(ncs.access_rates).length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-[#3D2B1F]/70 mb-2 uppercase">
            Benefits Access (NCS {ncs.year})
          </h4>
          <div className="flex flex-wrap gap-3">
            {Object.entries(ncs.access_rates).map(([key, rate]) => (
              <span key={key} className="text-xs text-[#3D2B1F]/70">
                <span className="font-medium">{key}:</span> {rate}%
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function NeighborhoodSection({ tract }) {
  if (!tract) return null

  return (
    <div className="mt-6 pt-4 border-t border-[#d9cebb]">
      <h3 className="text-sm font-bold text-[#3D2B1F] mb-1 uppercase tracking-wider">
        Neighborhood Demographics
      </h3>
      <p className="text-xs text-[#3D2B1F]/40 mb-4 italic">
        Area average for census tract {tract.tract_fips} -- not employer-specific data
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 mb-4">
        <MetricBox
          label="Median Income"
          value={tract.median_household_income ? `$${tract.median_household_income.toLocaleString()}` : null}
          sub="Household"
        />
        <MetricBox
          label="Unemployment Rate"
          value={tract.unemployment_rate != null ? `${tract.unemployment_rate}%` : null}
        />
        <MetricBox
          label="Population"
          value={tract.total_population?.toLocaleString()}
          sub="Census tract"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <DemographicSection title="Gender" items={tract.gender} />
        <DemographicSection title="Race/Ethnicity" items={tract.race} />
        <DemographicSection title="Hispanic/Latino" items={tract.hispanic} />
        <DemographicSection title="Education" items={tract.education} />
      </div>
    </div>
  )
}

function SourceBreakdownSection({ title, sourceData, sourceName }) {
  if (!sourceData) return null

  return (
    <details className="mt-4 group">
      <summary className="cursor-pointer text-xs font-semibold text-[#3D2B1F]/50 uppercase tracking-wider hover:text-[#3D2B1F]/70">
        {title} ({sourceName})
      </summary>
      <div className="mt-2 pl-2 border-l-2 border-[#E8DCC8]">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <DemographicSection title="Gender" items={sourceData.gender} />
          <DemographicSection title="Race/Ethnicity" items={sourceData.race?.filter(r => r.pct > 0)} />
          <DemographicSection title="Hispanic/Latino" items={sourceData.hispanic} />
          <DemographicSection title="Age" items={sourceData.age} />
          <DemographicSection title="Education" items={sourceData.education} />
        </div>
        <p className="text-xs text-[#3D2B1F]/30 mt-2 italic">
          {sourceData.total_workers
            ? `${sourceData.total_workers.toLocaleString()} estimated workers`
            : sourceData.total_jobs
              ? `${sourceData.total_jobs.toLocaleString()} total jobs`
              : ''}
          {sourceData.level === 'industry_broad' && ' (broad industry match)'}
          {sourceData.level === 'state' && ' (state-wide, no industry match)'}
        </p>
      </div>
    </details>
  )
}

export function WorkforceDemographicsCard({ state, naics, employerId }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['workforce-profile', employerId],
    queryFn: () => apiClient.get(`/api/profile/employers/${employerId}/workforce-profile`),
    enabled: !!employerId,
    staleTime: 1000 * 60 * 30,
  })

  if (!employerId) return null

  if (isLoading) return (
    <CollapsibleCard title="Workforce Demographics" defaultOpen={false}>
      <p className="text-sm text-[#3D2B1F]/50 italic">Loading workforce profile...</p>
    </CollapsibleCard>
  )

  if (isError || !data) return null

  const est = data.estimated_composition
  const hasEstimate = est && est.method !== 'none'
  const hasContext = data.qcew || data.soii || data.jolts || data.union_density || data.ncs

  if (!hasEstimate && !data.acs && !data.lodes && !hasContext && !data.tract) return null

  // Source availability badges
  const sources = [
    { label: 'ACS', available: !!data.acs },
    { label: 'LODES', available: !!data.lodes },
    { label: 'QCEW', available: !!data.qcew },
    { label: 'OES', available: !!data.oes },
    { label: 'SOII', available: !!data.soii },
    { label: 'JOLTS', available: !!data.jolts },
    { label: 'NCS', available: !!data.ncs },
    { label: 'CPS/Density', available: !!data.union_density },
    { label: 'Tract/ACS', available: !!data.tract },
  ]

  return (
    <CollapsibleCard title="Workforce Demographics" defaultOpen={false}>
      {/* Data source badges */}
      <div className="mb-4">
        {sources.map(s => (
          <DataSourceBadge key={s.label} label={s.label} available={s.available} />
        ))}
      </div>

      {/* Estimated composition - the headline */}
      {hasEstimate && (
        <div>
          <h3 className="text-sm font-bold text-[#3D2B1F] mb-1 uppercase tracking-wider">
            Estimated Workforce Composition
          </h3>
          <p className="text-xs text-[#3D2B1F]/50 mb-4 italic">
            {est.method === 'blended'
              ? `Blended from ACS (industry, ${Math.round(est.weights.acs * 100)}%) and LODES (county, ${Math.round(est.weights.lodes * 100)}%)`
              : est.method === 'acs_only'
                ? 'Based on ACS industry baseline (no LODES county data available)'
                : 'Based on LODES county data (no ACS industry data available)'}
          </p>

          {est.method === 'blended' || est.method === 'acs_only' || est.method === 'lodes_only' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <DemographicSection title="Gender" items={est.gender || est.demographics?.gender} />
              <DemographicSection title="Race/Ethnicity" items={(est.race || est.demographics?.race)?.filter(r => r.pct > 0)} />
              <DemographicSection title="Hispanic/Latino Origin" items={est.hispanic || est.demographics?.hispanic} />
              <DemographicSection title="Age Distribution" items={est.age || est.demographics?.age} />
              <DemographicSection title="Education" items={est.education || est.demographics?.education} />
            </div>
          ) : null}
        </div>
      )}

      {/* Industry & local context */}
      <IndustryContextSection data={data} />

      {/* Neighborhood demographics (census tract) */}
      <NeighborhoodSection tract={data.tract} />

      {/* Expandable source breakdowns */}
      <div className="mt-4 pt-3 border-t border-[#d9cebb]">
        <p className="text-xs text-[#3D2B1F]/40 uppercase tracking-wider mb-1 font-semibold">Source Data</p>
        <SourceBreakdownSection
          title="Industry Baseline"
          sourceData={data.acs}
          sourceName={`ACS${data.acs?.naics_matched ? ` NAICS ${data.acs.naics_matched}` : ''}`}
        />
        <SourceBreakdownSection
          title="County Workplace Average"
          sourceData={data.lodes}
          sourceName={`LODES county ${data.lodes?.county_fips || ''}`}
        />
      </div>
    </CollapsibleCard>
  )
}
