/**
 * FacilitiesLeafletMap
 *
 * Dynamically-imported inner map for FacilitiesMapCard. Kept in its own
 * module so that a) the Leaflet bundle is split out of the critical
 * profile-page chunk, b) jsdom-based tests can mock this default export
 * without pulling in `leaflet` (which depends on the DOM `Image`
 * constructor and matchMedia, both of which are flaky in the test env).
 *
 * Self-contained: takes the filtered `facilities` array + the
 * `sourceMeta` color map and renders a TileLayer + clustered markers.
 * Auto-fits to bounds on every facilities change.
 */
import { useEffect, useMemo } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import 'leaflet/dist/leaflet.css'

// Continental-US default view when there are zero markers (shouldn't
// happen since the parent card hides the map in that case, but render
// safely anyway).
const DEFAULT_CENTER = [39.8283, -98.5795]
const DEFAULT_ZOOM = 4

function FitBounds({ facilities }) {
  const map = useMap()
  useEffect(() => {
    if (!facilities || facilities.length === 0) return
    if (facilities.length === 1) {
      const f = facilities[0]
      map.setView([f.lat, f.lng], 10, { animate: false })
      return
    }
    const bounds = facilities.map((f) => [f.lat, f.lng])
    try {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 12, animate: false })
    } catch {
      // Defensive: bad data shouldn't crash the map.
    }
  }, [facilities, map])
  return null
}

function formatNumber(n) {
  if (n == null) return '—'
  return Number(n).toLocaleString()
}

function formatCurrency(n) {
  if (n == null) return null
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(n)
}

function FacilityPopup({ f, color }) {
  const addressLine = [f.address, f.city, f.state, f.zip].filter(Boolean).join(', ')
  const extra = f.extra || {}
  return (
    <div className="text-sm">
      <div className="flex items-center gap-2 font-semibold" style={{ color }}>
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: color }}
          aria-hidden="true"
        />
        {f.label}
      </div>
      {addressLine && <div className="mt-1 text-xs text-muted-foreground">{addressLine}</div>}
      {f.source === 'epa' && (
        <div className="mt-2 space-y-0.5 text-xs">
          {extra.snc_flag && (
            <div className="font-medium text-red-700">Significant non-complier</div>
          )}
          <div>Inspections: {formatNumber(extra.inspection_count)}</div>
          <div>Formal actions: {formatNumber(extra.formal_action_count)}</div>
          {extra.total_penalties > 0 && (
            <div>Penalties: {formatCurrency(extra.total_penalties)}</div>
          )}
        </div>
      )}
      {f.source === 'f7' && (
        <div className="mt-2 space-y-0.5 text-xs">
          {extra.latest_unit_size != null && (
            <div>Bargaining unit: {formatNumber(extra.latest_unit_size)}</div>
          )}
          {extra.latest_union_name && <div>Union: {extra.latest_union_name}</div>}
        </div>
      )}
      {f.source === 'mergent' && (
        <div className="mt-2 space-y-0.5 text-xs">
          {extra.location_type && <div>Type: {extra.location_type}</div>}
          {extra.employees_site != null && (
            <div>Site employees: {formatNumber(extra.employees_site)}</div>
          )}
        </div>
      )}
    </div>
  )
}

export default function FacilitiesLeafletMap({ facilities, sourceMeta }) {
  // Keyed by `${id}-${source}` to force React to drop CircleMarkers when
  // the visible-filter changes -- avoids stale popups bound to removed
  // markers.
  const markers = useMemo(() => facilities || [], [facilities])

  return (
    <MapContainer
      center={DEFAULT_CENTER}
      zoom={DEFAULT_ZOOM}
      scrollWheelZoom
      style={{ height: '100%', width: '100%' }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds facilities={markers} />
      <MarkerClusterGroup chunkedLoading maxClusterRadius={50}>
        {markers.map((f) => {
          const color = sourceMeta[f.source]?.color || '#2c2418'
          return (
            <CircleMarker
              key={f.id}
              center={[f.lat, f.lng]}
              radius={7}
              pathOptions={{
                color,
                fillColor: color,
                fillOpacity: 0.7,
                weight: 1,
              }}
            >
              <Popup>
                <FacilityPopup f={f} color={color} />
              </Popup>
            </CircleMarker>
          )
        })}
      </MarkerClusterGroup>
    </MapContainer>
  )
}
