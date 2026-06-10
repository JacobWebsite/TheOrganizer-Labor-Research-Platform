import { Building2, AlertTriangle, Loader2, ExternalLink } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { useMasterCompetitors } from '@/shared/api/profile'

// 24Q-15: CompetitorsCard. Surfaces the closest industry peers on the
// master profile, ranked by NAICS proximity (NAICS-6 first, falling back
// to NAICS-4) and workforce-size similarity (closest in log-employees).
//
// Each peer renders as a row: name -> link to peer's master profile,
// workers, scorecard tier badge, and the peer's full NAICS code. We
// keep this card visually distinct from ComparablesCard (which is the
// F7-side strategic-similarity view); this is the simple "who else is
// in your industry at your size?" answer.
//
// Empty states:
//  - No NAICS on the self row: "Industry classification not available"
//  - NAICS present but no peers in scorecard: "No peers found in this NAICS"

function formatNumber(n) {
  if (n == null) return '—'
  return Number(n).toLocaleString()
}

function tierBadge(tier) {
  if (!tier) return null
  // Mirror gold_standard_tier values from mv_target_scorecard:
  //   gold | silver | bronze | stub
  // We translate to a neutral label since "Strong/Promising/Speculative"
  // doesn't appear on the underlying tier; the frontend label is
  // capitalized to match other card chip styles.
  const map = {
    gold: { label: 'Gold', cls: 'bg-yellow-100 text-yellow-900' },
    silver: { label: 'Silver', cls: 'bg-slate-200 text-slate-900' },
    bronze: { label: 'Bronze', cls: 'bg-amber-100 text-amber-900' },
    stub: { label: 'Stub', cls: 'bg-muted text-muted-foreground' },
  }
  const e = map[tier] || { label: tier, cls: 'bg-muted text-muted-foreground' }
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] ${e.cls}`}
      title={`Scorecard tier: ${e.label}`}
    >
      {e.label}
    </span>
  )
}

export function CompetitorsCard({ masterId }) {
  const { data, isLoading, isError } = useMasterCompetitors(masterId)

  if (isLoading) {
    return (
      <CollapsibleCard icon={Building2} title="Industry Peers" summary="Loading...">
        <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Loading nearest peers...</span>
        </div>
      </CollapsibleCard>
    )
  }

  if (isError) {
    return (
      <CollapsibleCard icon={Building2} title="Industry Peers" summary="Error">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>Could not load industry peers.</p>
        </div>
      </CollapsibleCard>
    )
  }

  const naics = data?.naics
  const naicsLabel = data?.naics_label
  const sizeBand = data?.size_band
  const peers = data?.peers || []

  // No NAICS path -- self has no industry classification at all.
  if (!naics) {
    return (
      <CollapsibleCard
        icon={Building2}
        title="Industry Peers"
        summary="No NAICS available"
      >
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No industry classification (NAICS) is available for this employer, so we
            can't surface peers. NAICS coverage is highest among SEC filers,
            federal contractors, and 990 filers; private companies without those
            sources often appear empty here.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  // NAICS present but no peers in the scorecard.
  if (peers.length === 0) {
    return (
      <CollapsibleCard
        icon={Building2}
        title="Industry Peers"
        summary={`No peers in NAICS ${naics}`}
      >
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            We classified this employer as <strong>{naicsLabel || naics}</strong>{' '}
            (NAICS {naics}) but no other employers in the same NAICS have a
            scorecard row with a workforce count. This usually means the NAICS
            is rare or the only other masters in this code lack employer-count
            data.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  // Populated state: 12-row table with name -> profile link.
  const matchBasis = peers[0]?.match_basis === 'naics4' ? 'NAICS-4 prefix' : 'NAICS-6 exact'
  const summaryText = `${peers.length} peer${peers.length === 1 ? '' : 's'} · ${naicsLabel || naics}`

  return (
    <CollapsibleCard icon={Building2} title="Industry Peers" summary={summaryText}>
      <div className="space-y-4">
        <p className="text-xs italic text-muted-foreground">
          Closest industry peers ranked by workforce-size similarity within the
          same {matchBasis} (NAICS {naics}
          {naicsLabel ? ` — ${naicsLabel}` : ''}). Self is excluded.
          {sizeBand && sizeBand !== 'unknown' && (
            <> Self size band: <strong>{sizeBand}</strong>.</>
          )}
        </p>

        <div className="overflow-x-auto border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">Peer</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Workers</th>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">Tier</th>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">NAICS</th>
              </tr>
            </thead>
            <tbody>
              {peers.map((p) => (
                <tr key={p.master_id} className="border-b">
                  <td className="px-3 py-2 font-medium">
                    <a
                      href={`/employers/MASTER-${p.master_id}`}
                      className="inline-flex items-center gap-1 text-blue-700 hover:underline"
                      title={`Open ${p.name}'s master profile`}
                    >
                      {p.name}
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatNumber(p.consolidated_workers)}
                  </td>
                  <td className="px-3 py-2">{tierBadge(p.tier) || '—'}</td>
                  <td className="px-3 py-2 font-mono text-xs">{p.naics || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {data?.as_of && (
          <p className="text-xs text-muted-foreground">As of {data.as_of}</p>
        )}
      </div>
    </CollapsibleCard>
  )
}
