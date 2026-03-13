import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { FileText, ChevronDown, ChevronRight, ArrowLeft } from 'lucide-react'
import { useCBADocument } from '@/shared/api/cba'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import { cn } from '@/lib/utils'

function ConfidenceBadge({ confidence }) {
  if (confidence == null) return null
  const pct = Math.round(confidence * 100)
  const color = pct >= 80 ? 'bg-green-100 text-green-800'
    : pct >= 50 ? 'bg-yellow-100 text-yellow-800'
    : 'bg-red-100 text-red-800'
  return <span className={cn('text-xs px-1.5 py-0.5 rounded', color)}>{pct}%</span>
}

function ModalVerbBadge({ verb }) {
  if (!verb) return null
  const color = verb === 'shall' || verb === 'must' ? 'bg-blue-100 text-blue-800'
    : verb === 'may' ? 'bg-gray-100 text-gray-700'
    : 'bg-purple-100 text-purple-800'
  return <span className={cn('text-xs px-1.5 py-0.5 rounded', color)}>{verb}</span>
}

function ProvisionItem({ provision }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="border-b last:border-b-0 py-2">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-start gap-2 text-left"
      >
        {expanded
          ? <ChevronDown className="h-4 w-4 mt-0.5 shrink-0 text-[#8a7e6d]" />
          : <ChevronRight className="h-4 w-4 mt-0.5 shrink-0 text-[#8a7e6d]" />
        }
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{provision.provision_text?.slice(0, 120) || 'No text'}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <ConfidenceBadge confidence={provision.confidence_score} />
            <ModalVerbBadge verb={provision.modal_verb} />
            {provision.provision_class && (
              <span className="text-xs text-[#8a7e6d]">{provision.provision_class}</span>
            )}
          </div>
        </div>
      </button>
      {expanded && (
        <div className="ml-6 mt-2 space-y-2 text-sm">
          {provision.context_before && (
            <p className="text-[#8a7e6d] italic">{provision.context_before}</p>
          )}
          <p className="font-medium">{provision.provision_text}</p>
          {provision.context_after && (
            <p className="text-[#8a7e6d] italic">{provision.context_after}</p>
          )}
        </div>
      )}
    </div>
  )
}

function CategoryGroup({ category, provisions }) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="border rounded-lg">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/20 transition-colors"
      >
        <div className="flex items-center gap-2">
          {expanded
            ? <ChevronDown className="h-4 w-4 text-[#8a7e6d]" />
            : <ChevronRight className="h-4 w-4 text-[#8a7e6d]" />
          }
          <h3 className="font-editorial font-semibold">{category}</h3>
        </div>
        <span className="text-xs text-[#8a7e6d]">{provisions.length} provision{provisions.length !== 1 ? 's' : ''}</span>
      </button>
      {expanded && (
        <div className="px-4 pb-2">
          {provisions.map((p, i) => (
            <ProvisionItem key={p.provision_id || i} provision={p} />
          ))}
        </div>
      )}
    </div>
  )
}

export function CBADetail() {
  const { cbaId } = useParams()
  const { data, isLoading, isError, error } = useCBADocument(cbaId)

  const doc = data?.document || data || {}

  useEffect(() => {
    if (doc.employer_name_raw) {
      document.title = `${doc.employer_name_raw} Contract - The Organizer`
    }
  }, [doc.employer_name_raw])

  if (isLoading) return <PageSkeleton />

  if (isError) {
    return (
      <div className="border border-destructive/50 bg-destructive/5 rounded-lg p-4 text-sm text-destructive">
        Failed to load contract: {error?.message || 'Unknown error'}
      </div>
    )
  }

  if (!data) return null

  // Group provisions by category
  const provisions = data.provisions || []
  const grouped = {}
  for (const p of provisions) {
    const cat = p.category || 'Uncategorized'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(p)
  }
  const categoryOrder = Object.keys(grouped).sort()

  return (
    <div className="space-y-4">
      <Link to="/cbas" className="inline-flex items-center gap-1 text-sm text-[#c78c4e] hover:underline">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to contracts
      </Link>

      {/* Header */}
      <div className="border rounded-lg p-5">
        <div className="flex items-start gap-3">
          <FileText className="h-6 w-6 text-[#c78c4e] mt-0.5 shrink-0" />
          <div className="flex-1">
            <h1 className="font-editorial text-2xl font-bold">
              {doc.employer_name_raw || 'Unknown Employer'}
            </h1>
            {doc.union_name_raw && (
              <p className="text-[#8a7e6d] mt-0.5">{doc.union_name_raw}</p>
            )}
            <div className="flex flex-wrap gap-x-6 gap-y-1 mt-3 text-sm">
              {doc.effective_date && (
                <span><span className="text-[#8a7e6d]">Effective:</span> {doc.effective_date}</span>
              )}
              {doc.expiration_date && (
                <span><span className="text-[#8a7e6d]">Expires:</span> {doc.expiration_date}</span>
              )}
              {doc.page_count != null && (
                <span><span className="text-[#8a7e6d]">Pages:</span> {doc.page_count}</span>
              )}
              {doc.source_name && (
                <span><span className="text-[#8a7e6d]">Source:</span> {doc.source_name}</span>
              )}
            </div>
            {doc.employer_id && (
              <Link to={`/employers/${doc.employer_id}`} className="inline-block mt-2 text-sm text-[#c78c4e] hover:underline">
                View employer profile
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Provisions */}
      <div>
        <h2 className="font-editorial text-xl font-bold mb-3">
          Provisions ({provisions.length})
        </h2>
        {provisions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center border rounded-lg">
            <FileText className="h-10 w-10 text-muted-foreground mb-3" />
            <p className="text-muted-foreground">No provisions extracted yet.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {categoryOrder.map(cat => (
              <CategoryGroup key={cat} category={cat} provisions={grouped[cat]} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
