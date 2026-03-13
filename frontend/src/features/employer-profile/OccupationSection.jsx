import { useState } from 'react'
import { Briefcase, ChevronDown, ChevronRight } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'

function formatNumber(n) {
  if (n == null) return '--'
  return Number(n).toLocaleString()
}

function GrowthCell({ pct }) {
  if (pct == null) return <span className="text-[#3D2B1F]/40">--</span>
  const formatted = `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`
  if (pct > 0) return <span className="text-[#2d6a4f]">{formatted}</span>
  if (pct < 0) return <span className="text-[#c23a22]">{formatted}</span>
  return <span className="text-[#3D2B1F]/50">{formatted}</span>
}

const JOB_ZONE_LABELS = {
  1: 'Little or No Preparation',
  2: 'Some Preparation',
  3: 'Medium Preparation',
  4: 'Considerable Preparation',
  5: 'Extensive Preparation',
}

const JOB_ZONE_COLORS = {
  1: 'bg-[#E8DCC8] text-[#3D2B1F]',
  2: 'bg-[#d4c4a0] text-[#3D2B1F]',
  3: 'bg-[#8B6914] text-white',
  4: 'bg-[#6b4f0a] text-white',
  5: 'bg-[#3D2B1F] text-white',
}

function SkillBar({ name, value, max = 5 }) {
  const pct = value != null ? Math.min((value / max) * 100, 100) : 0
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-36 text-[#3D2B1F]/70 truncate" title={name}>{name}</span>
      <div className="flex-1 bg-[#E8DCC8] rounded h-3 overflow-hidden">
        <div
          className="bg-[#8B6914] h-full rounded transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right font-medium text-[#3D2B1F]">
        {value != null ? value.toFixed(1) : '--'}
      </span>
    </div>
  )
}

function OnetDetail({ occ }) {
  const skills = occ.top_skills || []
  const knowledge = occ.top_knowledge || []
  const context = occ.top_work_context || []
  const jobZone = occ.job_zone

  if (!skills.length && !knowledge.length && !context.length && jobZone == null) {
    return (
      <div className="px-3 py-2 text-xs text-[#3D2B1F]/50 italic">
        No O*NET data available for this occupation
      </div>
    )
  }

  return (
    <div className="px-3 py-3 bg-[#f5f0e8] border-t border-[#d9cebb]/30">
      <div className="flex flex-wrap gap-x-8 gap-y-3">
        {/* Job Zone Badge */}
        {jobZone != null && (
          <div className="w-full mb-1">
            <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${JOB_ZONE_COLORS[jobZone] || 'bg-gray-200'}`}>
              Zone {jobZone}: {JOB_ZONE_LABELS[jobZone] || 'Unknown'}
            </span>
          </div>
        )}

        {/* Skills */}
        {skills.length > 0 && (
          <div className="min-w-[240px] flex-1">
            <h5 className="text-xs font-semibold text-[#3D2B1F] mb-1 uppercase tracking-wide">Top Skills</h5>
            <div className="space-y-1">
              {skills.map((s, i) => (
                <SkillBar key={i} name={s.name} value={s.importance} />
              ))}
            </div>
          </div>
        )}

        {/* Knowledge */}
        {knowledge.length > 0 && (
          <div className="min-w-[240px] flex-1">
            <h5 className="text-xs font-semibold text-[#3D2B1F] mb-1 uppercase tracking-wide">Top Knowledge</h5>
            <div className="space-y-1">
              {knowledge.map((k, i) => (
                <SkillBar key={i} name={k.name} value={k.importance} />
              ))}
            </div>
          </div>
        )}

        {/* Work Context */}
        {context.length > 0 && (
          <div className="min-w-[240px] flex-1">
            <h5 className="text-xs font-semibold text-[#3D2B1F] mb-1 uppercase tracking-wide">Work Context</h5>
            <div className="space-y-1">
              {context.map((c, i) => (
                <SkillBar key={i} name={c.name} value={c.value} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function OccupationRow({ occ }) {
  const [expanded, setExpanded] = useState(false)
  const hasOnet = (occ.top_skills?.length > 0) || (occ.job_zone != null)

  return (
    <>
      <tr
        className={`border-t border-[#d9cebb]/50 ${hasOnet ? 'cursor-pointer hover:bg-[#f5f0e8]/50' : ''}`}
        onClick={() => hasOnet && setExpanded(!expanded)}
      >
        <td className="px-3 py-1.5 font-mono text-xs">
          <span className="flex items-center gap-1">
            {hasOnet && (
              expanded
                ? <ChevronDown className="h-3 w-3 text-[#3D2B1F]/50" />
                : <ChevronRight className="h-3 w-3 text-[#3D2B1F]/50" />
            )}
            {occ.occupation_code}
          </span>
        </td>
        <td className="px-3 py-1.5">{occ.occupation_title}</td>
        <td className="px-3 py-1.5 text-right">{formatNumber(occ.employment_2024)}</td>
        <td className="px-3 py-1.5 text-right">
          <GrowthCell pct={occ.employment_change_pct} />
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={4} className="p-0">
            <OnetDetail occ={occ} />
          </td>
        </tr>
      )}
    </>
  )
}

export function OccupationSection({ data, isLoading }) {
  const [showSimilar, setShowSimilar] = useState(false)

  if (isLoading) {
    return (
      <CollapsibleCard icon={Briefcase} title="Workforce Occupations" defaultOpen={false}>
        <p className="text-sm text-[#3D2B1F]/50 italic">Loading occupation data...</p>
      </CollapsibleCard>
    )
  }

  if (!data || !data.employer_naics) {
    return (
      <CollapsibleCard icon={Briefcase} title="Workforce Occupations" defaultOpen={false}>
        <div className="rounded border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          No NAICS code available for this employer
        </div>
      </CollapsibleCard>
    )
  }

  const occupations = data.top_occupations || []
  const similarIndustries = data.similar_industries || []

  return (
    <CollapsibleCard
      icon={Briefcase}
      title="Workforce Occupations"
      summary={occupations.length ? `${occupations.length} occupations` : undefined}
      defaultOpen={false}
    >
      {occupations.length === 0 ? (
        <div className="rounded border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          No BLS occupation data found for NAICS {data.employer_naics}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 text-left">
                <th className="px-3 py-2 font-medium">SOC Code</th>
                <th className="px-3 py-2 font-medium">Title</th>
                <th className="px-3 py-2 font-medium text-right">Employment (2024)</th>
                <th className="px-3 py-2 font-medium text-right">Growth %</th>
              </tr>
            </thead>
            <tbody>
              {occupations.map((occ) => (
                <OccupationRow key={occ.occupation_code} occ={occ} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {similarIndustries.length > 0 && (
        <div className="mt-4">
          <button
            onClick={() => setShowSimilar(!showSimilar)}
            className="flex items-center gap-1.5 text-sm font-medium text-[#3D2B1F]/70 hover:text-[#3D2B1F] transition-colors"
          >
            <ChevronDown className={`h-4 w-4 transition-transform ${showSimilar ? 'rotate-180' : ''}`} />
            Similar Industries ({similarIndustries.length})
          </button>
          {showSimilar && (
            <div className="overflow-x-auto mt-2">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted/50 text-left">
                    <th className="px-3 py-2 font-medium">Industry Code</th>
                    <th className="px-3 py-2 font-medium text-right">Overlap Score</th>
                    <th className="px-3 py-2 font-medium text-right">Shared Occupations</th>
                  </tr>
                </thead>
                <tbody>
                  {similarIndustries.map((ind) => (
                    <tr key={ind.similar_industry} className="border-t border-[#d9cebb]/50">
                      <td className="px-3 py-1.5 font-mono text-xs">{ind.similar_industry}</td>
                      <td className="px-3 py-1.5 text-right">
                        {ind.overlap_score != null ? `${(ind.overlap_score * 100).toFixed(1)}%` : '--'}
                      </td>
                      <td className="px-3 py-1.5 text-right">{ind.shared_occupations ?? '--'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </CollapsibleCard>
  )
}
