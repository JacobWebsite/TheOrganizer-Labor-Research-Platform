/**
 * EntityContextBlock (#44)
 *
 * Renders the unit / group / corporate-family worker counts returned by the
 * API's `entity_context` field. Prevents the Starbucks=119 / Walmart=10M
 * misread by labeling whichever number is primary and stacking the other
 * concepts as muted subtext.
 *
 * Expected prop shape (from api/services/entity_context.py):
 *   entityContext.display_mode: 'family_primary' | 'unit_primary'
 *   entityContext.unit:   { count, city, state, label } | null
 *   entityContext.group:  { count, member_count, canonical_name, label } | null
 *   entityContext.family: { primary_count, primary_source, sec_count,
 *                           mergent_count, ultimate_parent_name,
 *                           is_ultimate_parent_rollup, range, conflict,
 *                           label } | null
 *
 * Graceful fallback: if entityContext is null/undefined, renders the legacy
 * "X workers" chip so the UI never regresses behind the old single-number
 * display.
 */
import { Users, AlertTriangle } from 'lucide-react'

function formatNumber(n) {
  if (n == null) return null
  return Number(n).toLocaleString()
}

function formatCountDisplay(countOrRange) {
  // Accepts a bare number OR a range object { low, high, display }.
  if (countOrRange == null) return null
  if (typeof countOrRange === 'object' && countOrRange.display) {
    return countOrRange.display
  }
  return formatNumber(countOrRange)
}

function SourceSubLabel({ source }) {
  // Lightweight parenthetical source annotation.
  const LABEL = {
    sec_10k: 'SEC',
    mergent_company: 'Mergent',
    ppp_2020: 'PPP',
    rpe_estimate: 'est.',
    f7_group_consolidated: 'F7',
    f7_unit_size: 'F7 unit',
  }
  const label = LABEL[source]
  if (!label) return null
  return <span className="text-[10px] text-[#faf6ef]/40 ml-0.5">({label})</span>
}

function ConflictBadge({ conflict }) {
  if (!conflict?.present) return null
  const spread = conflict.spread_pct
  const title = `Sources disagree by ~${spread}%: ${conflict.sources_disagreeing?.join(' vs ') ?? 'SEC vs Mergent'}. Common cause: fiscal-year drift or domestic-vs-global reporting.`
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium bg-amber-100 text-amber-800 border border-amber-300 ml-1"
      title={title}
    >
      <AlertTriangle className="h-3 w-3" />
      sources disagree
    </span>
  )
}

function PrimaryCountRow({ count, label, source, conflict }) {
  const display = formatCountDisplay(count)
  if (!display) return null
  return (
    <span className="inline-flex items-center gap-1 text-sm text-[#faf6ef]/80">
      <Users className="h-3.5 w-3.5" />
      <span className="font-medium">{display}</span>
      <span className="text-[#faf6ef]/50">{label}</span>
      <SourceSubLabel source={source} />
      <ConflictBadge conflict={conflict} />
    </span>
  )
}

function SecondaryCountRow({ count, label, annotation }) {
  const display = formatCountDisplay(count)
  if (!display) return null
  return (
    <span className="inline-flex items-center gap-1 text-xs text-[#faf6ef]/50">
      <span>{display}</span>
      <span>{label}</span>
      {annotation ? <span className="text-[#faf6ef]/35">{annotation}</span> : null}
    </span>
  )
}

/**
 * Legacy fallback: the original single "{n} workers" chip. Used when the API
 * response predates #44 (entity_context is missing/null).
 */
function LegacyWorkersChip({ workers, sizeSource }) {
  if (workers == null) return null
  return (
    <span className="inline-flex items-center gap-1 text-sm text-[#faf6ef]/70">
      <Users className="h-3.5 w-3.5" />
      {formatNumber(workers)} workers
      {sizeSource === 'rpe_estimate' && (
        <span className="text-[10px] text-[#faf6ef]/40 ml-0.5">(RPE est.)</span>
      )}
    </span>
  )
}

export function EntityContextBlock({ entityContext, legacyWorkers, sizeSource }) {
  if (!entityContext) {
    return <LegacyWorkersChip workers={legacyWorkers} sizeSource={sizeSource} />
  }

  const { display_mode, unit, group, family } = entityContext
  const isFamilyPrimary = display_mode === 'family_primary' && family?.primary_count != null

  // Primary line is either family or unit.
  const primary = isFamilyPrimary
    ? {
        count: family.range || family.primary_count,
        label: family.label || 'Corp. Family',
        source: family.primary_source,
        conflict: family.conflict,
      }
    : unit
    ? {
        count: unit.count,
        label: unit.label || 'This unit',
        source: null,
        conflict: null,
      }
    : null

  if (!primary) {
    // No data at all - fall back to legacy (should be rare)
    return <LegacyWorkersChip workers={legacyWorkers} sizeSource={sizeSource} />
  }

  // Secondary lines: whichever concepts aren't primary.
  const secondaries = []
  if (isFamilyPrimary) {
    if (group?.count != null || group?.member_count != null) {
      const annotation =
        group.member_count && group.member_count > 0
          ? `${group.member_count} unit${group.member_count === 1 ? '' : 's'}`
          : null
      secondaries.push({
        key: 'group',
        count: group.count,
        label: group.label || 'Group',
        annotation,
      })
    }
    if (unit?.count != null) {
      const loc = [unit.city, unit.state].filter(Boolean).join(', ')
      secondaries.push({
        key: 'unit',
        count: unit.count,
        label: unit.label || 'This unit',
        annotation: loc || null,
      })
    }
  } else {
    // unit_primary: show group as secondary if it adds info, and family if present.
    if (group?.count != null || group?.member_count != null) {
      const annotation =
        group.member_count && group.member_count > 1
          ? `${group.member_count} units`
          : null
      secondaries.push({
        key: 'group',
        count: group.count,
        label: group.label || 'Group',
        annotation,
      })
    }
    if (family?.primary_count != null) {
      secondaries.push({
        key: 'family',
        count: family.range || family.primary_count,
        label: family.label || 'Corp. Family',
        annotation: family.is_ultimate_parent_rollup ? `roll-up: ${family.ultimate_parent_name}` : null,
      })
    }
  }

  return (
    <div className="inline-flex flex-col gap-0.5">
      <PrimaryCountRow
        count={primary.count}
        label={primary.label}
        source={primary.source}
        conflict={primary.conflict}
      />
      {secondaries.map((s) => (
        <SecondaryCountRow key={s.key} count={s.count} label={s.label} annotation={s.annotation} />
      ))}
    </div>
  )
}

export default EntityContextBlock
