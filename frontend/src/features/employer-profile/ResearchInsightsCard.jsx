import { useState } from 'react'
import { FlaskConical, ExternalLink, AlertTriangle, TrendingUp, Lightbulb, Clock } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useResearchResult } from '@/shared/api/research'
import { DossierSection } from '@/features/research/DossierSection'

function qualityColor(score) {
  if (score == null) return 'text-muted-foreground'
  if (score >= 7) return 'text-[#3a7d44]'
  if (score >= 5) return 'text-[#c78c4e]'
  return 'text-[#c23a22]'
}

function qualityLabel(score) {
  if (score == null) return 'Unknown'
  if (score >= 8) return 'Excellent'
  if (score >= 6.5) return 'Good'
  if (score >= 5) return 'Fair'
  return 'Limited'
}

function QualityBadge({ score }) {
  if (score == null) return null
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 w-16 bg-muted rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full', score >= 7 ? 'bg-[#3a7d44]' : score >= 5 ? 'bg-[#c78c4e]' : 'bg-[#c23a22]')}
          style={{ width: `${(score / 10) * 100}%` }}
        />
      </div>
      <span className={cn('text-sm font-semibold tabular-nums', qualityColor(score))}>
        {Number(score).toFixed(1)}
      </span>
      <span className="text-xs text-muted-foreground">{qualityLabel(score)}</span>
    </div>
  )
}

function ContradictionItem({ contradiction }) {
  const field = contradiction.field || contradiction.attribute || 'Unknown field'
  const dbVal = contradiction.db_value ?? contradiction.db ?? '-'
  const webVal = contradiction.web_value ?? contradiction.web ?? '-'

  return (
    <div className="flex items-start gap-2 text-sm py-1.5 border-b last:border-0">
      <AlertTriangle className="h-3.5 w-3.5 text-[#c78c4e] mt-0.5 shrink-0" />
      <div className="min-w-0">
        <span className="font-medium">{field.replace(/_/g, ' ')}</span>
        <div className="flex gap-4 text-xs text-muted-foreground mt-0.5">
          <span>Database: <span className="text-foreground">{String(dbVal)}</span></span>
          <span>Web: <span className="text-foreground">{String(webVal)}</span></span>
        </div>
      </div>
    </div>
  )
}

export function ResearchInsightsCard({ scorecard }) {
  const [showDossier, setShowDossier] = useState(false)

  const hasResearch = scorecard?.has_research
  const runId = scorecard?.research_run_id
  const quality = scorecard?.research_quality
  const approach = scorecard?.research_approach
  const trend = scorecard?.research_trend
  const contradictions = scorecard?.research_contradictions
  const delta = scorecard?.strategic_delta ?? scorecard?.score_delta

  // Fetch full dossier only when user expands it
  const dossierQuery = useResearchResult(runId, { enabled: showDossier && !!runId })

  // Dual-gate: show unverified notes for 5.0-6.9 quality runs
  const researchNotes = scorecard?.research_notes
  if (!hasResearch && !researchNotes) return null

  if (!hasResearch && researchNotes) {
    return (
      <CollapsibleCard icon={FlaskConical} title="Research Notes (Unverified)" summary={`Quality: ${Number(researchNotes.run_quality).toFixed(1)}/10`} defaultOpen={false}>
        <div className="space-y-3">
          <div className="flex items-center gap-2 px-3 py-2 bg-[#c78c4e]/10 border border-[#c78c4e]/30 rounded text-sm">
            <AlertTriangle className="h-4 w-4 text-[#c78c4e] shrink-0" />
            <span>Below verification threshold (7.0). Treat as unconfirmed leads.</span>
          </div>
          <div className="flex items-center gap-4">
            <div>
              <p className="text-xs text-muted-foreground mb-1">Research Quality</p>
              <QualityBadge score={researchNotes.run_quality} />
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">Run ID</p>
              <span className="text-sm font-mono">#{researchNotes.run_id}</span>
            </div>
          </div>
          {researchNotes.recommended_approach && (
            <div className="flex items-start gap-2">
              <Lightbulb className="h-4 w-4 text-[#c78c4e] mt-0.5 shrink-0" />
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-0.5">Suggested Approach</p>
                <p className="text-sm">{researchNotes.recommended_approach}</p>
              </div>
            </div>
          )}
          {researchNotes.financial_trend && (
            <div className="flex items-start gap-2">
              <TrendingUp className="h-4 w-4 text-[#3a6b8c] mt-0.5 shrink-0" />
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-0.5">Financial Trend</p>
                <p className="text-sm">{researchNotes.financial_trend}</p>
              </div>
            </div>
          )}
          {researchNotes.key_findings && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Key Findings</p>
              <pre className="text-xs bg-muted/50 p-3 rounded overflow-auto max-h-48 whitespace-pre-wrap">{researchNotes.key_findings}</pre>
            </div>
          )}
        </div>
      </CollapsibleCard>
    )
  }

  const contradictionList = Array.isArray(contradictions) ? contradictions : []
  const summary = quality != null
    ? `Quality: ${Number(quality).toFixed(1)}/10`
    : 'Research available'

  return (
    <CollapsibleCard icon={FlaskConical} title="Research Insights" summary={summary} defaultOpen>
      <div className="space-y-4">
        {/* Quality + delta row */}
        <div className="flex flex-wrap items-center gap-6">
          <div>
            <p className="text-xs text-muted-foreground mb-1">Research Quality</p>
            <QualityBadge score={quality} />
          </div>
          {delta != null && delta !== 0 && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">Score Impact</p>
              <span className={cn(
                'text-sm font-semibold',
                delta > 0 ? 'text-[#3a7d44]' : 'text-[#c23a22]'
              )}>
                {delta > 0 ? '+' : ''}{Number(delta).toFixed(2)}
              </span>
            </div>
          )}
          {runId && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">Run ID</p>
              <span className="text-sm font-mono">#{runId}</span>
            </div>
          )}
        </div>

        {/* Approach */}
        {approach && (
          <div className="flex items-start gap-2">
            <Lightbulb className="h-4 w-4 text-[#c78c4e] mt-0.5 shrink-0" />
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-0.5">Recommended Approach</p>
              <p className="text-sm">{approach}</p>
            </div>
          </div>
        )}

        {/* Trend */}
        {trend && (
          <div className="flex items-start gap-2">
            <TrendingUp className="h-4 w-4 text-[#3a6b8c] mt-0.5 shrink-0" />
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-0.5">Financial Trend</p>
              <p className="text-sm">{trend}</p>
            </div>
          </div>
        )}

        {/* Contradictions */}
        {contradictionList.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
              Source Contradictions ({contradictionList.length})
            </p>
            <div className="border rounded-md px-3 py-1">
              {contradictionList.map((c, i) => (
                <ContradictionItem key={i} contradiction={c} />
              ))}
            </div>
          </div>
        )}

        {/* Dossier toggle */}
        {runId && (
          <div className="pt-2 border-t">
            {!showDossier ? (
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => setShowDossier(true)}
              >
                <ExternalLink className="h-3.5 w-3.5" />
                View Full Research Dossier
              </Button>
            ) : dossierQuery.isLoading ? (
              <p className="text-sm text-muted-foreground animate-pulse">Loading dossier...</p>
            ) : dossierQuery.data?.dossier ? (
              <div className="space-y-3">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  Full Dossier - {dossierQuery.data.sections_by_key ? Object.keys(dossierQuery.data.sections_by_key).length : 0} sections
                </p>
                {Object.entries(dossierQuery.data.dossier).map(([sectionKey, sectionData]) => (
                  <DossierSection
                    key={sectionKey}
                    sectionKey={sectionKey}
                    facts={dossierQuery.data.sections_by_key?.[sectionKey] || []}
                    dossierData={dossierQuery.data.dossier}
                  />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Dossier not available.</p>
            )}
          </div>
        )}
      </div>
    </CollapsibleCard>
  )
}
