import { Info } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { ProfileHeader } from './ProfileHeader'
import { CrossReferencesSection } from './CrossReferencesSection'
import { QualityIndicator } from '@/features/scorecard/QualityIndicator'
import { DataProvenanceCard } from './DataProvenanceCard'

function EnrichmentSection({ title, children }) {
  return (
    <Card>
      <CardContent className="p-4">
        <h3 className="text-sm font-semibold mb-2">{title}</h3>
        {children}
      </CardContent>
    </Card>
  )
}

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

function formatCurrency(n) {
  if (n == null) return '\u2014'
  return '$' + Number(n).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function MasterProfileView({ data }) {
  const master = data.master || {}
  const enrichment = data.enrichment || {}
  const sourceIds = data.source_ids || []

  const employer = {
    employer_name: master.display_name || master.canonical_name,
    city: master.city,
    state: master.state,
    total_workers: master.employee_count,
    naics_code: master.naics,
  }

  const badges = []
  if (master.is_federal_contractor) badges.push('Federal Contractor')
  if (master.is_nonprofit) badges.push('Nonprofit')
  if (master.is_public) badges.push('Public Company')

  return (
    <div className="space-y-4">
      <ProfileHeader employer={employer} sourceType="MASTER" entityContext={data.entity_context} />

      {/* Quality + metadata */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-6">
            <div>
              <p className="text-xs text-muted-foreground mb-1">Data Quality</p>
              <QualityIndicator score={master.data_quality_score} />
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">Source</p>
              <span className="text-sm font-medium uppercase">{master.source_origin}</span>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">Sources Linked</p>
              <span className="text-sm font-medium">{master.source_count || 0}</span>
            </div>
            {master.ein && (
              <div>
                <p className="text-xs text-muted-foreground mb-1">EIN</p>
                <span className="text-sm font-medium">{master.ein}</span>
              </div>
            )}
            {badges.length > 0 && (
              <div className="flex gap-1.5">
                {badges.map((b) => (
                  <span key={b} className="inline-flex items-center px-2 py-0.5 text-xs font-medium border bg-muted">
                    {b}
                  </span>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Data Provenance */}
      <DataProvenanceCard matchSummary={data.match_summary} />

      {/* OSHA enrichment */}
      {enrichment.osha_summary && (
        <EnrichmentSection title="OSHA Summary">
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Establishments</p>
              <p className="font-medium">{formatNumber(enrichment.osha_summary.establishments)}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Total Violations</p>
              <p className="font-medium">{formatNumber(enrichment.osha_summary.total_violations)}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Total Penalties</p>
              <p className="font-medium">{formatCurrency(enrichment.osha_summary.total_penalties)}</p>
            </div>
          </div>
        </EnrichmentSection>
      )}

      {/* NLRB enrichment */}
      {enrichment.nlrb_summary && (
        <EnrichmentSection title="NLRB Summary">
          <p className="text-sm">
            <span className="font-medium">{formatNumber(enrichment.nlrb_summary.participants)}</span>
            <span className="text-muted-foreground"> participant records linked</span>
          </p>
        </EnrichmentSection>
      )}

      {/* WHD enrichment */}
      {enrichment.whd_summary && (
        <EnrichmentSection title="Wage & Hour (WHD) Summary">
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Cases</p>
              <p className="font-medium">{formatNumber(enrichment.whd_summary.case_count)}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Back Wages</p>
              <p className="font-medium">{formatCurrency(enrichment.whd_summary.backwages_amount)}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Civil Penalties</p>
              <p className="font-medium">{formatCurrency(enrichment.whd_summary.civil_penalties)}</p>
            </div>
          </div>
        </EnrichmentSection>
      )}

      {/* Scorecard enrichment (if linked to F7) */}
      {enrichment.scorecard && (
        <EnrichmentSection title="Organizing Scorecard">
          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            {enrichment.scorecard.score_tier && (
              <div>
                <p className="text-muted-foreground">Tier</p>
                <p className="font-medium">{enrichment.scorecard.score_tier}</p>
              </div>
            )}
            {enrichment.scorecard.weighted_score != null && (
              <div>
                <p className="text-muted-foreground">Score</p>
                <p className="font-medium">{Number(enrichment.scorecard.weighted_score).toFixed(1)}</p>
              </div>
            )}
          </div>
        </EnrichmentSection>
      )}
    </div>
  )
}

export function BasicProfileView({ data, isMaster = false }) {
  if (!data) return null

  if (isMaster) {
    return <MasterProfileView data={data} />
  }

  const employer = data.employer || {}
  const sourceType = data.source_type || 'UNKNOWN'

  return (
    <div className="space-y-4">
      <ProfileHeader employer={employer} sourceType={sourceType} entityContext={data.entity_context} />

      <Card>
        <CardContent className="p-4">
          <div className="flex items-start gap-2 text-sm text-muted-foreground">
            <Info className="h-4 w-4 mt-0.5 shrink-0" />
            <p>
              This employer was found via {sourceType} records. Limited data is available.
              Scorecard, OSHA, and detailed NLRB data are only available for employers in LM filing records (F7).
            </p>
          </div>
        </CardContent>
      </Card>

      <CrossReferencesSection crossReferences={data.cross_references} />
    </div>
  )
}
