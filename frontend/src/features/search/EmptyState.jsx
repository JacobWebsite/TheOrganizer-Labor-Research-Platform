import { SearchX } from 'lucide-react'

export function EmptyState({ query }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <SearchX className="h-12 w-12 text-muted-foreground mb-4" />
      <h3 className="text-lg font-semibold mb-1">No results found</h3>
      <p className="text-muted-foreground mb-2">
        {query
          ? <>No employers matching &ldquo;{query}&rdquo;.</>
          : <>No results found.</>
        }
      </p>
      <p className="text-sm text-muted-foreground">
        Try broadening your search or adjusting your filters.
      </p>
    </div>
  )
}
