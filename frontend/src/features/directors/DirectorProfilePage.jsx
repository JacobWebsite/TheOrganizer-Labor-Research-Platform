import { Link, useParams } from 'react-router-dom'
import { Loader2, AlertTriangle, ArrowLeft, ExternalLink } from 'lucide-react'
import { useDirectorProfile } from '@/shared/api/profile'

// Director permalink page. Fed by /api/directors/{slug}. Renders the
// boards a director serves on plus per-board context (since-year,
// committees, independence, source proxy URL).
//
// Linked from BoardCard interlock rows on the master profile (each
// interlock row's director name becomes a clickable Link).

export function DirectorProfilePage() {
  const { slug } = useParams()
  const { data, isLoading, isError, error } = useDirectorProfile(slug)

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading director profile…
        </div>
      </div>
    )
  }

  if (isError) {
    const status = error?.status || error?.response?.status
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <Link
          to="/search"
          className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-3 w-3" /> Back
        </Link>
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <div>
            <p className="font-medium">
              {status === 404 ? 'Director not found' : 'Could not load director'}
            </p>
            <p className="mt-1 text-xs">
              {status === 404
                ? `No director matched the slug "${slug}". This may mean the parser hasn't seen them in any DEF14A filing yet, or the name as written doesn't pass our quality filter.`
                : 'There was a problem reaching the API. Please try again.'}
            </p>
          </div>
        </div>
      </div>
    )
  }

  const summary = data?.summary || {}
  const boards = data?.boards || []
  const namesMatched = data?.names_matched || []
  const displayName = namesMatched[0] || slug

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <Link
        to="/search"
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3 w-3" /> Back to search
      </Link>

      <header className="mb-6 border-b pb-4">
        <h1 className="text-2xl font-bold">{displayName}</h1>
        {namesMatched.length > 1 && (
          <p className="mt-1 text-xs italic text-muted-foreground">
            Also recorded as: {namesMatched.slice(1).join(', ')}
          </p>
        )}
        <p className="mt-2 text-sm text-muted-foreground">
          Director on{' '}
          <span className="font-medium text-foreground">{summary.boards_count}</span>{' '}
          {summary.boards_count === 1 ? 'company board' : 'company boards'}
          {summary.is_independent_count > 0 &&
            <> · {summary.is_independent_count} as independent director</>}
          {summary.earliest_since_year && summary.latest_since_year && (
            <> · serving since {summary.earliest_since_year}
              {summary.latest_since_year > summary.earliest_since_year &&
                ` (most recent appointment ${summary.latest_since_year})`}
            </>
          )}
        </p>
      </header>

      <section>
        <h2 className="mb-3 text-sm font-medium">Board memberships</h2>
        {boards.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No board memberships were extracted from DEF14A filings for this
            director.
          </p>
        ) : (
          <ul className="divide-y">
            {boards.map((b) => (
              <li key={b.master_id} className="py-3">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <Link
                      to={`/employers/MASTER-${b.master_id}`}
                      className="font-medium hover:underline"
                    >
                      {b.canonical_name || `Master ${b.master_id}`}
                    </Link>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {b.state && <span>{b.state}</span>}
                      {b.naics && (
                        <span className="ml-2 font-mono">NAICS {b.naics}</span>
                      )}
                      {b.is_independent === true && (
                        <span className="ml-2 rounded bg-green-100 px-1.5 py-0.5 font-mono text-[10px] text-green-900">
                          IND
                        </span>
                      )}
                      {b.is_independent === false && (
                        <span className="ml-2 rounded bg-blue-100 px-1.5 py-0.5 font-mono text-[10px] text-blue-900">
                          INSIDE
                        </span>
                      )}
                    </div>
                    <div className="mt-1 text-xs">
                      {b.since_year && <span>Director since {b.since_year}</span>}
                      {b.position && (
                        <span className="ml-2 italic text-muted-foreground">
                          {b.position}
                        </span>
                      )}
                    </div>
                    {b.committees && b.committees.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {b.committees.map((c, i) => (
                          <span
                            key={i}
                            className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                          >
                            {c}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  {b.source_url && (
                    <a
                      href={b.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex-shrink-0 text-xs text-muted-foreground hover:text-foreground"
                      title="Source DEF14A filing"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="mt-8 text-xs italic text-muted-foreground">
        Data extracted from SEC DEF14A proxy filings. Coverage is concentrated
        in publicly-traded companies that file annual proxies; private companies
        and most non-profits will not appear here.
      </p>
    </div>
  )
}
