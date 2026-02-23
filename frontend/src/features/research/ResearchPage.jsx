import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Microscope, SearchX, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import { HelpSection } from '@/shared/components/HelpSection'
import { useResearchRuns, useStartResearch } from '@/shared/api/research'
import { useResearchState } from './useResearchState'
import { ResearchFilters } from './ResearchFilters'
import { ResearchRunsTable } from './ResearchRunsTable'
import { NewResearchModal } from './NewResearchModal'

export function ResearchPage() {
  const navigate = useNavigate()
  const [modalOpen, setModalOpen] = useState(false)
  const { filters, page, PAGE_SIZE, hasActiveFilters, setFilter, clearFilter, clearAll, setPage } = useResearchState()

  const { data, isLoading, isError, error } = useResearchRuns({
    status: filters.status || undefined,
    q: filters.q || undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  })

  const startMutation = useStartResearch()

  function handleStartResearch(formData) {
    startMutation.mutate(formData, {
      onSuccess: (result) => {
        setModalOpen(false)
        navigate(`/research/${result.run_id}`)
      },
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Microscope className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">Research Deep Dives</h1>
        </div>
        <Button size="sm" className="gap-1.5" onClick={() => setModalOpen(true)}>
          <Plus className="h-4 w-4" />
          New Research
        </Button>
      </div>

      <HelpSection>
        <p><strong>What this does:</strong> An AI research agent queries 10+ internal databases to build a comprehensive dossier on any company in 30-120 seconds.</p>
        <p><strong>What you get:</strong> ~30 facts across 7 sections covering identity, labor history, financial standing, government contracts, legal actions, industry context, and an overall assessment.</p>
        <p><strong>Cost:</strong> Each run costs approximately $0.02-0.03 in API usage.</p>
      </HelpSection>

      <ResearchFilters
        filters={filters}
        hasActiveFilters={hasActiveFilters}
        onSetFilter={setFilter}
        onClearFilter={clearFilter}
        onClearAll={clearAll}
      />

      {isLoading && !data && <PageSkeleton variant="research" />}

      {isError && (
        <div className="border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
          Failed to load research runs: {error?.message || 'Unknown error'}
        </div>
      )}

      {data && data.total === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <SearchX className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-1">No research runs found</h3>
          {hasActiveFilters ? (
            <p className="text-muted-foreground mb-4">
              Try adjusting your filters or search term.
            </p>
          ) : (
            <p className="text-muted-foreground mb-4">
              Start your first deep dive to research a company.
            </p>
          )}
          {!hasActiveFilters && (
            <Button size="sm" className="gap-1.5" onClick={() => setModalOpen(true)}>
              <Plus className="h-4 w-4" />
              New Research
            </Button>
          )}
        </div>
      )}

      {data && data.total > 0 && (
        <>
          <p className="text-sm text-muted-foreground">
            {data.total.toLocaleString()} run{data.total !== 1 ? 's' : ''} found
          </p>
          <ResearchRunsTable
            runs={data.runs}
            total={data.total}
            page={page}
            pageSize={PAGE_SIZE}
            onPageChange={setPage}
          />
        </>
      )}

      {modalOpen && (
        <NewResearchModal
          onSubmit={handleStartResearch}
          isPending={startMutation.isPending}
          error={startMutation.isError ? startMutation.error : null}
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  )
}
