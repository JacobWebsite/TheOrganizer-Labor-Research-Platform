import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { GitCompareArrows, SearchX, X } from 'lucide-react'
import { useCBADocuments, useCBACompare } from '@/shared/api/cba'

const MAX_COMPARE = 4

export function CBACompare() {
  useEffect(() => { document.title = 'Compare Contracts - The Organizer' }, [])

  const [selectedIds, setSelectedIds] = useState([])
  const [searchTerm, setSearchTerm] = useState('')

  const documentsQuery = useCBADocuments({ employer: searchTerm || undefined, limit: 50 })
  const compareQuery = useCBACompare(selectedIds)

  const toggleContract = (id) => {
    setSelectedIds(prev => {
      if (prev.includes(id)) return prev.filter(x => x !== id)
      if (prev.length >= MAX_COMPARE) return prev
      return [...prev, id]
    })
  }

  const removeContract = (id) => {
    setSelectedIds(prev => prev.filter(x => x !== id))
  }

  const documents = documentsQuery.data?.results || []
  const comparison = compareQuery.data
  const compDocs = comparison?.documents || []
  const compCategories = comparison?.categories || []

  return (
    <div className="space-y-4">
      <h1 className="font-editorial text-3xl font-bold">Compare Contracts</h1>
      <p className="text-sm text-[#8a7e6d]">Select 2-4 contracts to compare side by side.</p>

      {/* Selected contracts */}
      {selectedIds.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selectedIds.map(id => {
            const doc = documents.find(d => d.cba_id === id)
            return (
              <span
                key={id}
                className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm"
                style={{ borderColor: '#c78c4e' }}
              >
                {doc?.employer_name_raw || `Contract #${id}`}
                <button type="button" onClick={() => removeContract(id)} className="hover:text-destructive">
                  <X className="h-3 w-3" />
                </button>
              </span>
            )
          })}
        </div>
      )}

      {/* Contract selector */}
      <div className="border rounded-lg p-4">
        <input
          type="text"
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          placeholder="Search contracts by employer name..."
          className="w-full rounded border px-3 py-1.5 text-sm bg-transparent mb-3"
        />
        {documentsQuery.isLoading && <p className="text-sm text-[#8a7e6d]">Loading...</p>}
        {documents.length > 0 && (
          <div className="max-h-60 overflow-y-auto space-y-1">
            {documents.map(doc => {
              const isSelected = selectedIds.includes(doc.cba_id)
              const isDisabled = !isSelected && selectedIds.length >= MAX_COMPARE
              return (
                <label
                  key={doc.cba_id}
                  className={`flex items-center gap-2 px-2 py-1.5 rounded text-sm cursor-pointer hover:bg-muted/30 ${isDisabled ? 'opacity-40 cursor-not-allowed' : ''}`}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleContract(doc.cba_id)}
                    disabled={isDisabled}
                    className="accent-[#c78c4e]"
                  />
                  <span className="flex-1">{doc.employer_name_raw || 'Unknown'}</span>
                  <span className="text-xs text-[#8a7e6d]">{doc.union_name_raw || ''}</span>
                </label>
              )
            })}
          </div>
        )}
        {documents.length === 0 && !documentsQuery.isLoading && (
          <p className="text-sm text-[#8a7e6d]">No contracts found.</p>
        )}
      </div>

      {/* Comparison view */}
      {selectedIds.length < 2 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <GitCompareArrows className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="font-editorial text-lg font-semibold mb-1">Select contracts to compare</h3>
          <p className="text-muted-foreground">Choose at least 2 contracts from the list above.</p>
        </div>
      )}

      {compareQuery.isLoading && selectedIds.length >= 2 && (
        <p className="text-sm text-[#8a7e6d]">Loading comparison...</p>
      )}

      {compareQuery.isError && (
        <div className="border border-destructive/50 bg-destructive/5 rounded-lg p-4 text-sm text-destructive">
          Comparison failed: {compareQuery.error?.message || 'Unknown error'}
        </div>
      )}

      {comparison && compCategories.length > 0 && (
        <div className="space-y-4">
          <h2 className="font-editorial text-xl font-bold">
            Comparison ({compDocs.length} contracts, {compCategories.length} categories)
          </h2>

          {compCategories.map(catGroup => (
            <div key={catGroup.category} className="border rounded-lg overflow-hidden">
              <div className="px-4 py-2 bg-muted/30 border-b">
                <h3 className="font-editorial font-semibold">{catGroup.category}</h3>
              </div>
              <div className="grid" style={{ gridTemplateColumns: `repeat(${compDocs.length}, 1fr)` }}>
                {compDocs.map(cdoc => {
                  const provisions = (catGroup.provisions || []).filter(p => p.cba_id === cdoc.cba_id)
                  return (
                    <div key={cdoc.cba_id} className="border-r last:border-r-0 p-3">
                      <div className="mb-2">
                        <Link
                          to={`/cbas/${cdoc.cba_id}`}
                          className="text-xs font-medium text-[#c78c4e] hover:underline"
                        >
                          {cdoc.employer_name_raw || 'Unknown'}
                        </Link>
                      </div>
                      {provisions.length === 0 ? (
                        <p className="text-xs text-[#8a7e6d] italic">No provisions in this category</p>
                      ) : (
                        <div className="space-y-2">
                          {provisions.map((p, i) => (
                            <p key={p.provision_id || i} className="text-xs leading-relaxed">
                              {p.provision_text?.slice(0, 200)}
                              {(p.provision_text?.length || 0) > 200 ? '...' : ''}
                            </p>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {comparison && compCategories.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <SearchX className="h-10 w-10 text-muted-foreground mb-3" />
          <p className="text-muted-foreground">No provisions found in the selected contracts.</p>
        </div>
      )}
    </div>
  )
}
