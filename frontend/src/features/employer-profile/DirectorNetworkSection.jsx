import { useState } from 'react'
import { Network, ChevronRight, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useDirectorNetwork } from '@/shared/api/profile'

// 24Q-14 C.2-3: Director Network Section. Renders the corporate-power-map
// view as a section right under BoardCard. Two tables:
//   - 1-hop: companies that directly share a director with the anchor
//   - 2-hop: companies connected via a 1-hop neighbor (capped at top 50)
//
// Self-gates: hidden entirely if the anchor has fewer than 3 1-hop
// neighbors (small private companies + recent IPOs would otherwise
// render an unhelpful "1 connection" surface). The endpoint returns
// `stats.should_surface` as the recommended gate.

const VISIBLE_ONE_HOP = 8
const VISIBLE_TWO_HOP = 10

function NaicsTag({ naics }) {
  if (!naics) return null
  return (
    <span className="ml-2 font-mono text-[10px] text-muted-foreground">
      NAICS {naics}
    </span>
  )
}

export function DirectorNetworkSection({ masterId }) {
  const [expandOneHop, setExpandOneHop] = useState(false)
  const [expandTwoHop, setExpandTwoHop] = useState(false)
  const { data, isLoading, isError } = useDirectorNetwork(masterId)

  if (isLoading || isError) return null
  if (!data?.stats?.should_surface) return null

  const oneHop = data.one_hop || []
  const twoHop = data.two_hop || []
  const sharedDirectors = data.shared_directors || []
  const visibleOneHop = expandOneHop ? oneHop : oneHop.slice(0, VISIBLE_ONE_HOP)
  const visibleTwoHop = expandTwoHop ? twoHop : twoHop.slice(0, VISIBLE_TWO_HOP)

  return (
    <section className="mt-6 rounded border bg-card">
      <header className="border-b p-4">
        <div className="flex items-start gap-2">
          <Network className="mt-0.5 h-4 w-4 flex-shrink-0 text-muted-foreground" />
          <div>
            <h3 className="text-sm font-semibold">Director Network</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Companies linked to{' '}
              <span className="font-medium">{data.anchor.canonical_name}</span>{' '}
              through shared board directors. Use this to see "who controls
              this company AND what else do they control."
            </p>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-3 text-center">
          <div>
            <div className="text-xl font-bold">{data.stats.shared_directors_total}</div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Shared Directors
            </div>
          </div>
          <div>
            <div className="text-xl font-bold">{data.stats.one_hop_count}</div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Direct Companies
            </div>
          </div>
          <div>
            <div className="text-xl font-bold">{data.stats.two_hop_count}</div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              2-Hop Companies
            </div>
          </div>
        </div>
      </header>

      <div className="space-y-4 p-4">
        {sharedDirectors.length > 0 && (
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Shared Directors
            </h4>
            <div className="flex flex-wrap gap-1.5">
              {sharedDirectors.map((sd) => (
                <a
                  key={sd.slug}
                  href={`/directors/${sd.slug}`}
                  className="rounded bg-blue-50 px-2 py-1 text-xs text-blue-900 hover:bg-blue-100"
                  title={`See all boards ${sd.name} serves on`}
                >
                  {sd.name}
                </a>
              ))}
            </div>
          </div>
        )}

        {oneHop.length > 0 && (
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Directly Connected ({oneHop.length})
            </h4>
            <ul className="divide-y">
              {visibleOneHop.map((c) => (
                <li key={c.master_id} className="py-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <a
                        href={`/employers/MASTER-${c.master_id}`}
                        className="text-sm font-medium text-blue-700 hover:underline"
                      >
                        {c.canonical_name || `Master ${c.master_id}`}
                      </a>
                      {c.state && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          {c.state}
                        </span>
                      )}
                      <NaicsTag naics={c.naics} />
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        Shared{' '}
                        {c.shared_director_count === 1 ? 'director' : 'directors'}:{' '}
                        {c.shared_directors.join(', ')}
                      </div>
                    </div>
                    <span className="flex-shrink-0 rounded bg-muted px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
                      {c.shared_director_count}{' '}
                      {c.shared_director_count === 1 ? 'link' : 'links'}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
            {oneHop.length > VISIBLE_ONE_HOP && (
              <Button
                variant="ghost"
                size="sm"
                className="mt-1 w-full"
                onClick={() => setExpandOneHop((v) => !v)}
              >
                {expandOneHop
                  ? `Show top ${VISIBLE_ONE_HOP}`
                  : `Show all ${oneHop.length} direct connections`}
              </Button>
            )}
          </div>
        )}

        {twoHop.length > 0 && (
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              2-Hop Connections ({data.stats.two_hop_count})
              {data.stats.two_hop_count > data.stats.two_hop_returned && (
                <span className="ml-1 normal-case text-muted-foreground/80">
                  · top {data.stats.two_hop_returned} shown
                </span>
              )}
            </h4>
            <p className="mb-2 text-xs italic text-muted-foreground">
              Companies one director-hop away. Sorted by how many distinct
              paths from the anchor reach each company — more paths means
              tighter governance overlap.
            </p>
            <ul className="divide-y">
              {visibleTwoHop.map((c) => (
                <li key={c.master_id} className="py-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <a
                        href={`/employers/MASTER-${c.master_id}`}
                        className="text-sm text-blue-700 hover:underline"
                      >
                        {c.canonical_name || `Master ${c.master_id}`}
                      </a>
                      {c.state && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          {c.state}
                        </span>
                      )}
                      <NaicsTag naics={c.naics} />
                    </div>
                    <span className="flex-shrink-0 rounded bg-muted px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
                      {c.via_company_count}{' '}
                      {c.via_company_count === 1 ? 'path' : 'paths'}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
            {twoHop.length > VISIBLE_TWO_HOP && (
              <Button
                variant="ghost"
                size="sm"
                className="mt-1 w-full"
                onClick={() => setExpandTwoHop((v) => !v)}
              >
                {expandTwoHop
                  ? `Show top ${VISIBLE_TWO_HOP}`
                  : `Show top ${twoHop.length} 2-hop connections`}
              </Button>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
