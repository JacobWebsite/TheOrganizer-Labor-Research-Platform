import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import { useResearchStatus, useResearchResult, useStartResearch } from '@/shared/api/research'
import { DossierHeader } from './DossierHeader'
import { DossierSection } from './DossierSection'
import { ActionLog } from './ActionLog'

const SECTION_ORDER = [
  'identity',
  'labor',
  'assessment',
  'workforce',
  'workplace',
  'financial',
  'sources',
]

export function ResearchResultPage() {
  const { runId } = useParams()
  const navigate = useNavigate()

  const statusQuery = useResearchStatus(runId)
  const status = statusQuery.data

  const isCompleted = status?.status === 'completed'
  const isFailed = status?.status === 'failed'

  const resultQuery = useResearchResult(runId, { enabled: isCompleted })
  const result = resultQuery.data

  const startMutation = useStartResearch()

  function handleRunAgain() {
    if (!status?.company_name) return
    startMutation.mutate(
      { company_name: status.company_name },
      {
        onSuccess: (data) => navigate(`/research/${data.run_id}`),
      }
    )
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
          <h2 className="text-xl font-semibold mb-1">Research run not found</h2>
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
          <h2 className="text-xl font-semibold mb-1">Something went wrong</h2>
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

  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
        <ArrowLeft className="h-4 w-4" />
        Back
      </Button>

      <DossierHeader status={status} onRunAgain={handleRunAgain} />

      {/* Failed state */}
      {isFailed && (
        <div className="border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
          Research failed: {status?.current_step || 'Unknown error'}
        </div>
      )}

      {/* Completed: show dossier sections */}
      {isCompleted && result && (
        <>
          {result.quality_score != null && (
            <p className="text-sm text-muted-foreground">
              Overall quality: <span className="font-medium">{Math.round(result.quality_score * 100)}%</span>
              {' '}&middot;{' '}
              {result.total_facts} fact{result.total_facts !== 1 ? 's' : ''} across {result.sections_filled} section{result.sections_filled !== 1 ? 's' : ''}
            </p>
          )}

          {SECTION_ORDER.map((sectionKey) => (
            <DossierSection
              key={sectionKey}
              sectionKey={sectionKey}
              facts={result.facts_by_section?.[sectionKey]}
              dossierData={dossierSections}
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
