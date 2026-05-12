import { AlertTriangle } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'

/**
 * EmptyStateCard -- the canonical "we checked and found nothing" component
 * for the employer profile and union profile pages.
 *
 * Why this exists (2026-05-12):
 *   Before this card, the profile had three competing conventions for
 *   absence-of-data:
 *     - Some sections rendered a collapsible card with an amber warning
 *       panel (OSHA, NLRB, WHD, NYC, BoardCard, ExecutivesCard, ...).
 *     - Some sections silently returned null (ComparablesCard,
 *       CorporateHierarchyCard, DataProvenanceCard, CrossReferencesSection,
 *       UnionRelationshipsCard, ResearchInsightsCard).
 *     - Some did neither and rendered an empty container.
 *   That inconsistency hides a critical UX truth for labor organizers:
 *   "no data" and "no violations" are NOT the same thing. A clean OSHA
 *   record is a meaningful signal; a missing data match is a matching
 *   limitation. The amber panel pattern makes this distinction explicit.
 *
 * Convention:
 *   - Every employer profile card shows itself even with no data.
 *   - The empty state is collapsed by default with summary "No <topic>
 *     records matched" (or a card-supplied override).
 *   - When the user expands the card, they see an amber panel with the
 *     "no matched != no exists" caveat plus an optional, card-specific
 *     "reason" string explaining the coverage limit.
 *
 * Props:
 *   icon -- lucide icon component (passed through to CollapsibleCard).
 *   title -- card title.
 *   topic -- short noun phrase for the empty-state copy (e.g. "OSHA",
 *            "Federal lobbying", "Board"). Used in the body sentence
 *            'No <topic> records have been matched to this employer.'
 *   summary -- optional override for the collapsed-state summary text.
 *              Defaults to 'No records matched'.
 *   reason -- optional ReactNode appended to the amber panel that
 *             explains coverage limits (e.g. "DEF14A coverage is
 *             limited to publicly traded companies"). Renders as a
 *             second sentence inside the same paragraph.
 *   defaultOpen / storageKey -- forwarded to CollapsibleCard.
 *
 * Tests:
 *   __tests__/ProfileCards.test.jsx (EmptyStateCard convention block)
 *   exercises the shape; per-card tests assert their own empty-state
 *   copy when relevant.
 */
export function EmptyStateCard({
  icon,
  title,
  topic,
  summary = 'No records matched',
  reason,
  defaultOpen = false,
  storageKey,
}) {
  return (
    <CollapsibleCard
      icon={icon}
      title={title}
      summary={summary}
      defaultOpen={defaultOpen}
      storageKey={storageKey}
    >
      <div
        className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
        data-empty-state="true"
      >
        <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
        <p>
          No {topic} records have been matched to this employer. This does{' '}
          <strong>not</strong> mean none exist &mdash; it may mean our matching has not yet
          connected this employer to those records.
          {reason ? <> {reason}</> : null}
        </p>
      </div>
    </CollapsibleCard>
  )
}
