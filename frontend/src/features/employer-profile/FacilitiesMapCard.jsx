/**
 * FacilitiesMapCard
 *
 * Week 3 A.2 (ROADMAP_2026_05_04_to_2026_07_05_LAUNCH.md). Renders a
 * Leaflet map on the master profile that shows the employer's physical
 * footprint: EPA ECHO facilities, F-7 bargaining-unit addresses, and
 * Mergent corporate sites. Markers are color-coded per source and the
 * source layers can be toggled. Markers cluster when zoomed out.
 *
 * Data flows from `useMasterFacilities` (re-exported via
 * `./hooks/useFacilities`). OSHA + NY ABO are omitted -- neither has
 * lat/lng in the warehouse today; geocoding them is a separate effort.
 *
 * Lazy-loads `react-leaflet` so the Leaflet bundle never lands in the
 * critical path of an employer profile that has zero facilities. The
 * underlying `leaflet` CSS is also lazy-imported in the same module.
 */
import { lazy, Suspense, useMemo, useState } from 'react'
import { MapPin, Loader2, AlertTriangle } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useMasterFacilities } from '@/shared/api/profile'

// Source palette mirrors the Aged Broadsheet token list in CLAUDE.md.
// EPA -> brick red (enforcement), F-7 -> editorial teal (union),
// Mergent -> copper accent (corporate).
const SOURCE_META = {
  epa: { label: 'EPA Facilities', color: '#c23a22' },
  f7: { label: 'F-7 Workplaces', color: '#1a6b5a' },
  mergent: { label: 'Mergent Sites', color: '#c78c4e' },
}

const SOURCE_ORDER = ['epa', 'f7', 'mergent']

function formatNumber(n) {
  if (n == null) return '—'
  return Number(n).toLocaleString()
}

// Lazy-loaded inner map. Pulling react-leaflet (and the leaflet CSS)
// behind a dynamic import keeps profiles with no facilities from paying
// for the ~140 KB Leaflet bundle.
const FacilitiesLeafletMap = lazy(() => import('./FacilitiesLeafletMap.jsx'))

function LegendDot({ color, label, count, active, onToggle }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        'inline-flex items-center gap-1.5 border px-2 py-1 text-xs font-medium transition',
        active ? 'opacity-100' : 'opacity-40',
      )}
      style={{
        borderColor: color,
        background: active ? `${color}10` : 'transparent',
      }}
      aria-pressed={active}
    >
      <span
        className="inline-block h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color }}
        aria-hidden="true"
      />
      <span>{label}</span>
      <span className="text-muted-foreground">({formatNumber(count)})</span>
    </button>
  )
}

export function FacilitiesMapCard({ masterId }) {
  const { data, isLoading, isError } = useMasterFacilities(masterId)

  // Per-source visibility toggles. Default: all on.
  const [visibleSources, setVisibleSources] = useState({ epa: true, f7: true, mergent: true })

  const facilities = data?.facilities || []
  const summary = data?.summary || {}
  const bySource = summary.by_source || { epa: 0, f7: 0, mergent: 0 }
  const totalFacilities = summary.total_facilities ?? facilities.length

  const visibleFacilities = useMemo(() => {
    if (!facilities.length) return []
    return facilities.filter((f) => visibleSources[f.source] !== false)
  }, [facilities, visibleSources])

  function toggleSource(source) {
    setVisibleSources((prev) => ({ ...prev, [source]: !prev[source] }))
  }

  if (isLoading) {
    return (
      <CollapsibleCard icon={MapPin} title="Facilities Map" summary="Loading...">
        <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Loading facility locations...</span>
        </div>
      </CollapsibleCard>
    )
  }

  if (isError) {
    return (
      <CollapsibleCard icon={MapPin} title="Facilities Map" summary="Error">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>Could not load facility locations. The map data may still be loading on the server.</p>
        </div>
      </CollapsibleCard>
    )
  }

  // Empty state -- no geocoded facilities matched. Surface the same
  // "no data != no presence" UX as EnvironmentalCard.
  if (totalFacilities === 0) {
    return (
      <CollapsibleCard icon={MapPin} title="Facilities Map" summary="No geocoded locations">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No geocoded facilities have been matched to this employer. This does <strong>not</strong>{' '}
            mean the employer has no physical footprint &mdash; only sources that carry lat/lng in
            our warehouse (EPA, F-7, Mergent) are mapped here. OSHA inspection sites and state
            contract addresses exist as text but are not geocoded yet.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  // Card is opened by default when there's actually a map to draw.
  const summaryText = `${formatNumber(totalFacilities)} location${totalFacilities === 1 ? '' : 's'}`
  const stateList = Array.isArray(summary.states) && summary.states.length > 0
    ? summary.states.join(', ')
    : null

  return (
    <CollapsibleCard
      icon={MapPin}
      title="Facilities Map"
      summary={summaryText}
      defaultOpen
      storageKey="facilities-map-card-open"
    >
      <div className="space-y-4">
        {/* Header row: total + per-state list */}
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
          <span className="font-semibold">{formatNumber(totalFacilities)} locations</span>
          {stateList && (
            <span className="text-muted-foreground">across {stateList}</span>
          )}
        </div>

        {/* Layer toggles. Click a chip to hide/show that source. */}
        <div className="flex flex-wrap gap-2" role="group" aria-label="Toggle facility sources">
          {SOURCE_ORDER.map((source) => {
            const count = bySource[source] || 0
            if (count === 0) return null
            const meta = SOURCE_META[source]
            return (
              <LegendDot
                key={source}
                color={meta.color}
                label={meta.label}
                count={count}
                active={!!visibleSources[source]}
                onToggle={() => toggleSource(source)}
              />
            )
          })}
        </div>

        {/* Map. Suspense fallback covers the dynamic-import window for
            Leaflet's bundle. The map itself self-handles fitBounds and
            clustering. */}
        <div className="h-96 w-full overflow-hidden border border-border">
          <Suspense
            fallback={
              <div className="flex h-full w-full items-center justify-center bg-muted/30 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Loading map...
              </div>
            }
          >
            <FacilitiesLeafletMap
              facilities={visibleFacilities}
              sourceMeta={SOURCE_META}
            />
          </Suspense>
        </div>

        {visibleFacilities.length === 0 && totalFacilities > 0 && (
          <p className="text-xs text-muted-foreground">
            All sources hidden &mdash; click a chip above to show locations.
          </p>
        )}

        <Button
          variant="ghost"
          size="sm"
          onClick={() => setVisibleSources({ epa: true, f7: true, mergent: true })}
          className="w-full"
          disabled={Object.values(visibleSources).every(Boolean)}
        >
          Reset filters
        </Button>

        <p className="text-xs text-muted-foreground">
          Map shows EPA ECHO facilities, F-7 bargaining-unit addresses, and Mergent corporate sites
          for which lat/lng is available. OSHA inspection sites and state contracts are not yet
          geocoded.
        </p>
      </div>
    </CollapsibleCard>
  )
}
