import { useSearchParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Trophy, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import { useCompareRuns, useSubmitComparison } from '@/shared/api/research'
import { cn } from '@/lib/utils'

function qualityColor(score) {
  if (score == null) return ''
  if (score >= 7) return 'text-[#3a7d44]'
  if (score >= 5) return 'text-[#c78c4e]'
  return 'text-[#c23a22]'
}

function RunColumn({ run, isWinner, onPickWinner, isPending }) {
  return (
    <Card className={cn(isWinner && 'ring-2 ring-[#3a7d44]')}>
      <CardContent className="pt-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-editorial text-lg font-semibold">Run #{run.id}</h3>
          {isWinner ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded bg-[#3a7d44]/15 text-[#3a7d44] border border-[#3a7d44]/30">
              <Trophy className="h-3 w-3" /> Winner
            </span>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={onPickWinner}
              disabled={isPending}
              className="gap-1.5 text-xs"
            >
              <Trophy className="h-3 w-3" />
              Pick Winner
            </Button>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">Quality</p>
            <p className={cn('font-medium', qualityColor(run.overall_quality_score))}>
              {run.overall_quality_score != null ? `${Number(run.overall_quality_score).toFixed(1)}/10` : '-'}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Facts</p>
            <p className="font-medium">{run.total_facts_found ?? '-'}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Sections</p>
            <p className="font-medium">{run.sections_filled != null ? `${run.sections_filled}/10` : '-'}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Duration</p>
            <p className="font-medium">
              {run.duration_seconds != null
                ? run.duration_seconds < 60
                  ? `${Math.round(run.duration_seconds)}s`
                  : `${Math.floor(run.duration_seconds / 60)}m ${Math.round(run.duration_seconds % 60)}s`
                : '-'}
            </p>
          </div>
        </div>

        {/* Quality dimensions */}
        {run.quality_dimensions && (
          <div className="mt-3 pt-3 border-t border-muted space-y-1.5">
            {[
              { key: 'source_quality', label: 'Source Quality' },
              { key: 'coverage', label: 'Coverage' },
              { key: 'actionability', label: 'Actionability' },
              { key: 'consistency', label: 'Consistency' },
              { key: 'freshness', label: 'Freshness' },
              { key: 'efficiency', label: 'Efficiency' },
            ].map(({ key, label }) => {
              const val = run.quality_dimensions[key]
              if (val == null) return null
              return (
                <div key={key} className="flex items-center gap-2 text-xs">
                  <span className="w-24 text-muted-foreground">{label}</span>
                  <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className={cn('h-full rounded-full', val >= 7 ? 'bg-[#3a7d44]' : val >= 5 ? 'bg-[#c78c4e]' : 'bg-[#c23a22]')}
                      style={{ width: `${(val / 10) * 100}%` }}
                    />
                  </div>
                  <span className="w-6 text-right font-medium">{val.toFixed(1)}</span>
                </div>
              )
            })}
          </div>
        )}

        {/* Sections breakdown */}
        {run.sections && run.sections.length > 0 && (
          <div className="mt-3 pt-3 border-t border-muted">
            <h4 className="text-xs font-semibold text-muted-foreground mb-1.5">Facts by Section</h4>
            <div className="space-y-1">
              {run.sections.map(s => (
                <div key={s.dossier_section} className="flex items-center justify-between text-xs">
                  <span className="capitalize text-muted-foreground">{s.dossier_section}</span>
                  <span className="font-medium">
                    {s.fact_count} fact{s.fact_count !== 1 ? 's' : ''}
                    {s.reviewed_count > 0 && (
                      <span className="text-muted-foreground ml-1">({s.reviewed_count} reviewed)</span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Usefulness */}
        {run.run_usefulness != null && (
          <div className="mt-3 pt-3 border-t border-muted">
            <span className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded border ${
              run.run_usefulness
                ? 'bg-[#3a7d44]/15 text-[#3a7d44] border-[#3a7d44]/30'
                : 'bg-[#c23a22]/15 text-[#c23a22] border-[#c23a22]/30'
            }`}>
              {run.run_usefulness ? 'Marked Useful' : 'Marked Not Useful'}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function CompareRunsPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const runIdA = searchParams.get('a')
  const runIdB = searchParams.get('b')

  const comparisonQuery = useCompareRuns(runIdA, runIdB, {
    enabled: !!runIdA && !!runIdB,
  })
  const submitMutation = useSubmitComparison()

  const data = comparisonQuery.data
  const winnerRunId = data?.existing_comparison?.winner_run_id || submitMutation.data?.winner_run_id

  function handlePickWinner(winnerId) {
    submitMutation.mutate({
      run_id_a: Number(runIdA),
      run_id_b: Number(runIdB),
      winner_run_id: winnerId,
    })
  }

  const handleBack = () => {
    if (window.history.length > 1) {
      navigate(-1)
    } else {
      navigate('/research')
    }
  }

  if (!runIdA || !runIdB) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <AlertTriangle className="h-12 w-12 text-muted-foreground mb-4" />
          <h2 className="font-editorial text-xl font-semibold mb-1">Missing run IDs</h2>
          <p className="text-sm text-muted-foreground">
            Provide both run IDs: /research/compare?a=X&b=Y
          </p>
        </div>
      </div>
    )
  }

  if (comparisonQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <PageSkeleton />
      </div>
    )
  }

  if (comparisonQuery.isError) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
          <h2 className="font-editorial text-xl font-semibold mb-1">Failed to load comparison</h2>
          <p className="text-sm text-muted-foreground mb-4">
            {comparisonQuery.error?.message || 'Could not load run comparison data.'}
          </p>
          <Button variant="outline" size="sm" onClick={() => comparisonQuery.refetch()}>
            Retry
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={handleBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <h1 className="font-editorial text-xl font-bold">
          Compare: {data?.run_a?.company_name || `Run ${runIdA}`}
        </h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <RunColumn
          run={data?.run_a || {}}
          isWinner={winnerRunId === data?.run_a?.id}
          onPickWinner={() => handlePickWinner(data.run_a.id)}
          isPending={submitMutation.isPending}
        />
        <RunColumn
          run={data?.run_b || {}}
          isWinner={winnerRunId === data?.run_b?.id}
          onPickWinner={() => handlePickWinner(data.run_b.id)}
          isPending={submitMutation.isPending}
        />
      </div>

      {submitMutation.isSuccess && (
        <div className="border border-[#3a7d44]/30 bg-[#3a7d44]/5 rounded-lg p-3 text-sm text-[#3a7d44]">
          Comparison saved. Winner: Run #{winnerRunId}
        </div>
      )}
    </div>
  )
}
