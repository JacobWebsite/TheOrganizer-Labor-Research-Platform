import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Flag, Download, AlertTriangle, Microscope, Printer } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { FlagModal } from './FlagModal'
import { useStartResearch, useResearchStatus } from '@/shared/api/research'

function exportProfileCsv(employer, scorecard, entityContext) {
  const now = new Date().toISOString().split('T')[0]
  const ec = entityContext || {}
  const unit = ec.unit || {}
  const group = ec.group || {}
  const family = ec.family || {}
  const conflict = family.conflict || {}
  const rows = [
    ['Field', 'Value'],
    ['Export Date', now],
    ['Name', employer?.employer_name || ''],
    ['City', employer?.city || ''],
    ['State', employer?.state || ''],
    ['ZIP', employer?.zip || ''],
    ['Workers', employer?.consolidated_workers || employer?.unit_size || ''],
    ['Size Source', scorecard?.size_source || ''],
    ['Unit Workers', unit.count ?? ''],
    ['Unit Location', [unit.city, unit.state].filter(Boolean).join(', ')],
    ['Group Workers', group.count ?? ''],
    ['Group Member Count', group.member_count ?? ''],
    ['Corp Family Primary', family.primary_count ?? ''],
    ['Corp Family Source', family.primary_source ?? ''],
    ['Corp Family SEC', family.sec_count ?? ''],
    ['Corp Family Mergent', family.mergent_count ?? ''],
    ['Ultimate Parent', family.ultimate_parent_name ?? ''],
    ['Sources Conflict', conflict.present ? `Yes (${conflict.spread_pct}% spread)` : 'No'],
    ['NAICS', employer?.naics_code || employer?.naics || ''],
    ['Union', employer?.union_name || employer?.latest_union_name || 'None'],
    ['Score Tier', scorecard?.score_tier || ''],
    ['Weighted Score', scorecard?.weighted_score ?? ''],
    ['OSHA Score', scorecard?.score_osha ?? ''],
    ['NLRB Score', scorecard?.score_nlrb ?? ''],
    ['WHD Score', scorecard?.score_whd ?? ''],
    ['Contracts Score', scorecard?.score_contracts ?? ''],
    ['Union Proximity Score', scorecard?.score_union_proximity ?? ''],
    ['Financial Score', scorecard?.score_financial ?? ''],
    ['Size Score', scorecard?.score_size ?? ''],
    ['Similarity Score', scorecard?.score_similarity ?? ''],
    ['Anger Pillar', scorecard?.score_anger ?? ''],
    ['Leverage Pillar', scorecard?.score_leverage ?? ''],
    ['Factors Available', scorecard?.factors_available ?? ''],
    ['Coverage %', scorecard?.coverage_pct ?? ''],
    ['Has OSHA', scorecard?.has_osha ?? ''],
    ['Has NLRB', scorecard?.has_nlrb ?? ''],
    ['Has WHD', scorecard?.has_whd ?? ''],
    ['Has Research', scorecard?.has_research ?? ''],
    ['Has Compound Enforcement', scorecard?.has_compound_enforcement ?? ''],
    ['Has Child Labor', scorecard?.has_child_labor ?? ''],
    ['WHD Repeat Violator', scorecard?.is_whd_repeat_violator ?? ''],
    ['Has Close Election', scorecard?.has_close_election ?? ''],
    ['Recommended Action', scorecard?.recommended_action || ''],
  ]
  const csv = rows.map((r) => r.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${(employer?.employer_name || 'employer').replace(/[^a-z0-9]/gi, '_')}_profile.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export function ProfileActionButtons({ employer, scorecard, entityContext }) {
  const [flagOpen, setFlagOpen] = useState(false)
  const [flagType, setFlagType] = useState(null)
  const [researchRunId, setResearchRunId] = useState(null)
  const navigate = useNavigate()

  const employerId = employer?.employer_id || employer?.canonical_id
  const startResearch = useStartResearch()

  // Poll research status while a run is in progress
  const statusQuery = useResearchStatus(researchRunId, { enabled: !!researchRunId })
  const researchStatus = statusQuery.data?.status

  // Update toast when research status changes
  useEffect(() => {
    if (!researchRunId) return

    if (researchStatus === 'running') {
      toast.loading(`Researching ${employer?.employer_name || 'company'}...`, {
        id: `research-${researchRunId}`,
        description: statusQuery.data?.current_step,
      })
    } else if (researchStatus === 'completed') {
      toast.success('Research complete!', {
        id: `research-${researchRunId}`,
        description: `${statusQuery.data?.total_facts_found || 0} facts found`,
        action: {
          label: 'View Dossier',
          onClick: () => navigate(`/research/${researchRunId}`),
        },
      })
      setResearchRunId(null)
    } else if (researchStatus === 'failed') {
      toast.error('Research failed', {
        id: `research-${researchRunId}`,
        description: statusQuery.data?.current_step,
      })
      setResearchRunId(null)
    }
  }, [researchStatus, researchRunId, statusQuery.data, employer?.employer_name, navigate])

  if (!employerId) return null

  function handleDeepDive() {
    const name = employer?.employer_name || employer?.participant_name || ''
    if (!name) return

    startResearch.mutate(
      {
        company_name: name,
        employer_id: employerId,
        naics_code: employer?.naics_code || employer?.naics || undefined,
        state: employer?.state || undefined,
      },
      {
        onSuccess: (result) => {
          setResearchRunId(result.run_id)
          toast.loading(`Starting research on ${name}...`, {
            id: `research-${result.run_id}`,
          })
        },
        onError: (err) => {
          toast.error(`Failed to start research: ${err.message}`)
        },
      }
    )
  }

  return (
    <>
      <div className="flex items-center gap-2 mt-4 pt-4 border-t">
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => { setFlagType(null); setFlagOpen(true) }}
        >
          <Flag className="h-3.5 w-3.5" />
          Flag as Target
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => exportProfileCsv(employer, scorecard, entityContext)}
        >
          <Download className="h-3.5 w-3.5" />
          Export Data
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => window.print()}
          data-print-keep
        >
          <Printer className="h-3.5 w-3.5" />
          Print Profile
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={handleDeepDive}
          disabled={startResearch.isPending || !!researchRunId}
        >
          <Microscope className="h-3.5 w-3.5" />
          {startResearch.isPending ? 'Starting...' : researchRunId ? 'Researching...' : 'Deep Dive'}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 text-amber-600 hover:text-amber-700"
          onClick={() => { setFlagType('DATA_QUALITY'); setFlagOpen(true) }}
        >
          <AlertTriangle className="h-3.5 w-3.5" />
          Something Looks Wrong
        </Button>
      </div>

      {flagOpen && (
        <FlagModal
          sourceType="F7"
          sourceId={employerId}
          initialFlagType={flagType}
          onClose={() => setFlagOpen(false)}
        />
      )}
    </>
  )
}
