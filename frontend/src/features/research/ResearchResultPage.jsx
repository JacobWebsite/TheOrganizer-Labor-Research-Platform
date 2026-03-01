import { useEffect, useState } from 'react'
import { useParams, useNavigate, useOutletContext } from 'react-router-dom'
import { ArrowLeft, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import {
  useResearchStatus, useResearchResult, useStartResearch,
  useReviewFact, useReviewSummary, useSetHumanScore,
} from '@/shared/api/research'
import { DossierHeader } from './DossierHeader'
import { DossierSection } from './DossierSection'
import { ActionLog } from './ActionLog'
import { cn } from '@/lib/utils'

const SECTION_ORDER = [
  'identity',
  'labor',
  'assessment',
  'workforce',
  'workplace',
  'financial',
  'sources',
]

function qualityColor(score) {
  if (score == null) return ''
  if (score >= 7) return 'text-[#3a7d44]'
  if (score >= 5) return 'text-[#c78c4e]'
  return 'text-[#c23a22]'
}

function qualityBarColor(val) {
  if (val >= 7) return 'bg-[#3a7d44]'
  if (val >= 5) return 'bg-[#c78c4e]'
  return 'bg-[#c23a22]'
}

export function ResearchResultPage() {
  const { runId } = useParams()
  const navigate = useNavigate()
  const { setBreadcrumbs } = useOutletContext() || {}

  const statusQuery = useResearchStatus(runId)
  const status = statusQuery.data

  const isCompleted = status?.status === 'completed'
  const isFailed = status?.status === 'failed'

  // Set custom breadcrumbs with company name
  const companyName = status?.company_name
  useEffect(() => {
    if (setBreadcrumbs && companyName) {
      setBreadcrumbs([
        { label: 'Research', to: '/research' },
        { label: `${companyName} Dossier` },
      ])
    }
  }, [setBreadcrumbs, companyName])

  const resultQuery = useResearchResult(runId, { enabled: isCompleted })
  const result = resultQuery.data

  const startMutation = useStartResearch()
  const reviewMutation = useReviewFact()
  const reviewSummary = useReviewSummary(runId, { enabled: isCompleted })
  const humanScoreMutation = useSetHumanScore()

  const [humanScore, setHumanScore] = useState('')

  // Sync human score from API result
  useEffect(() => {
    if (result?.human_quality_score != null) {
      setHumanScore(String(result.human_quality_score))
    }
  }, [result?.human_quality_score])

  function handleRunAgain() {
    if (!status?.company_name) return
    startMutation.mutate(
      { company_name: status.company_name },
      {
        onSuccess: (data) => navigate(`/research/${data.run_id}`),
      }
    )
  }

  function handleReviewFact(factId, verdict) {
    reviewMutation.mutate({ factId, verdict })
  }

  function handleHumanScoreBlur() {
    const val = parseFloat(humanScore)
    if (isNaN(val) || val < 0 || val > 10) return
    if (val === result?.human_quality_score) return
    humanScoreMutation.mutate({ runId: Number(runId), human_quality_score: val })
  }

  const handleBack = () => {
    if (window.history.length > 1) {
      navigate(-1)
    } else {
      navigate('/research')
    }
  }

  // Initial loading
  if (statusQuery.isLoading && !status) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <PageSkeleton variant="research-result" />
      </div>
    )
  }

  // 404
  if (statusQuery.isError && statusQuery.error?.status === 404) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <AlertTriangle className="h-12 w-12 text-muted-foreground mb-4" />
          <h2 className="font-editorial text-xl font-semibold mb-1">Research run not found</h2>
          <p className="text-sm text-muted-foreground">
            No research run with ID "{runId}" exists.
          </p>
        </div>
      </div>
    )
  }

  // Generic error
  if (statusQuery.isError) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
          <h2 className="font-editorial text-xl font-semibold mb-1">Something went wrong</h2>
          <p className="text-sm text-muted-foreground mb-4">
            {statusQuery.error?.message || 'Failed to load research run.'}
          </p>
          <Button variant="outline" size="sm" onClick={() => statusQuery.refetch()}>
            Retry
          </Button>
        </div>
      </div>
    )
  }

  // The dossier JSON is nested: result.dossier = { facts, dossier: { identity, labor, ... }, skipped_tools }
  const dossierSections = result?.dossier?.dossier || result?.dossier || {}

  const summary = reviewSummary.data

  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
        <ArrowLeft className="h-4 w-4" />
        Back
      </Button>

      <DossierHeader status={status} onRunAgain={handleRunAgain} />

      {/* Failed state */}
      {isFailed && (
        <div className="border border-destructive/50 bg-destructive/5 rounded-lg p-4 text-sm text-destructive">
          Research failed: {status?.current_step || 'Unknown error'}
        </div>
      )}

      {/* Completed: show dossier sections */}
      {isCompleted && result && (
        <>
          {result.quality_score != null && (
            <div className="border rounded-lg p-4 bg-card">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-editorial text-sm font-semibold">Research Quality</h3>
                <span className={cn('text-2xl font-bold', qualityColor(result.quality_score))}>
                  {result.quality_score.toFixed(1)}<span className="text-sm font-normal text-muted-foreground">/10</span>
                </span>
              </div>
              {result.quality_dimensions && (
                <div className="space-y-2">
                  {[
                    { key: 'source_quality', label: 'Source Quality', weight: '35%' },
                    { key: 'coverage', label: 'Coverage', weight: '20%' },
                    { key: 'actionability', label: 'Actionability', weight: '15%' },
                    { key: 'consistency', label: 'Consistency', weight: '15%' },
                    { key: 'freshness', label: 'Freshness', weight: '10%' },
                    { key: 'efficiency', label: 'Efficiency', weight: '5%' },
                  ].map(({ key, label, weight }) => {
                    const val = result.quality_dimensions[key]
                    if (val == null) return null
                    return (
                      <div key={key} className="flex items-center gap-2 text-sm">
                        <span className="w-28 text-muted-foreground shrink-0">{label} <span className="text-xs">({weight})</span></span>
                        <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className={cn('h-full rounded-full', qualityBarColor(val))}
                            style={{ width: `${(val / 10) * 100}%` }}
                          />
                        </div>
                        <span className="w-8 text-right font-medium">{val.toFixed(1)}</span>
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Review progress */}
              {summary && summary.total_facts > 0 && (
                <div className="mt-3 pt-3 border-t border-muted">
                  <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
                    <span>Fact review progress</span>
                    <span>{summary.reviewed}/{summary.total_facts} reviewed</span>
                  </div>
                  <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[#c78c4e] rounded-full transition-all"
                      style={{ width: `${(summary.reviewed / summary.total_facts) * 100}%` }}
                    />
                  </div>
                  {summary.reviewed > 0 && (
                    <div className="flex gap-3 mt-1.5 text-[10px] text-muted-foreground">
                      {summary.confirmed > 0 && <span className="text-[#3a7d44]">{summary.confirmed} confirmed</span>}
                      {summary.rejected > 0 && <span className="text-[#c23a22]">{summary.rejected} rejected</span>}
                      {summary.irrelevant > 0 && <span>{summary.irrelevant} irrelevant</span>}
                    </div>
                  )}
                </div>
              )}

              {/* Human quality score */}
              <div className="mt-3 pt-3 border-t border-muted flex items-center gap-3">
                <label htmlFor="human-score" className="text-xs text-muted-foreground whitespace-nowrap">
                  Human score
                </label>
                <input
                  id="human-score"
                  type="number"
                  min="0"
                  max="10"
                  step="0.5"
                  value={humanScore}
                  onChange={(e) => setHumanScore(e.target.value)}
                  onBlur={handleHumanScoreBlur}
                  placeholder="0-10"
                  className="w-16 text-sm px-2 py-0.5 border rounded bg-background text-center"
                />
                <span className="text-[10px] text-muted-foreground">/10</span>
                {humanScoreMutation.isPending && (
                  <span className="text-[10px] text-muted-foreground">Saving...</span>
                )}
              </div>

              <p className="text-xs text-muted-foreground mt-3">
                {result.total_facts} fact{result.total_facts !== 1 ? 's' : ''} across {result.sections_filled} section{result.sections_filled !== 1 ? 's' : ''}
              </p>
            </div>
          )}

          {SECTION_ORDER.map((sectionKey) => (
            <DossierSection
              key={sectionKey}
              sectionKey={sectionKey}
              facts={result.facts_by_section?.[sectionKey]}
              dossierData={dossierSections}
              onReviewFact={handleReviewFact}
            />
          ))}

          <ActionLog actions={result.action_log} />
        </>
      )}

      {/* Loading result after status shows completed */}
      {isCompleted && resultQuery.isLoading && (
        <PageSkeleton variant="research-result" />
      )}
    </div>
  )
}
