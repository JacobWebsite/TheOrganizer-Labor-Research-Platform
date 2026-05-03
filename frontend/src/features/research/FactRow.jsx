import { ThumbsUp, ThumbsDown, Minus, AlertTriangle, Flag, MoreHorizontal } from 'lucide-react'
import { questionFor, isNotFoundValue } from './questionMap'

function formatValue(value, valueJson) {
  if (valueJson != null) {
    if (Array.isArray(valueJson)) {
      if (valueJson.length === 0) return '-'
      if (typeof valueJson[0] === 'string') return valueJson.join(', ')
      if (typeof valueJson[0] === 'object') {
        const preview = Object.entries(valueJson[0]).map(([k, v]) => `${k}: ${v}`).join(', ')
        return `${valueJson.length} record(s) — ${preview}`
      }
      return valueJson.join(', ')
    }
    if (typeof valueJson === 'object') {
      return Object.entries(valueJson).map(([k, v]) => `${k}: ${v}`).join(', ')
    }
  }
  return value || '-'
}

function confidenceBorder(confidence) {
  if (confidence == null) return 'border-l-[#d9cebb]'
  if (confidence >= 0.7) return 'border-l-[#3a7d44]'
  if (confidence >= 0.4) return 'border-l-[#c78c4e]'
  return 'border-l-[#d9cebb]'
}

const VERDICT_BADGE = {
  confirmed: { label: 'Confirmed', className: 'bg-[#3a7d44]/15 text-[#3a7d44] border-[#3a7d44]/30' },
  rejected:  { label: 'Rejected',  className: 'bg-[#c23a22]/15 text-[#c23a22] border-[#c23a22]/30' },
  irrelevant:{ label: 'Irrelevant',className: 'bg-[#8a7e6d]/15 text-[#8a7e6d] border-[#8a7e6d]/30' },
}

export function FactRow({ fact, onReview }) {
  const question = questionFor(fact.attribute_name)
  const value = formatValue(fact.attribute_value, fact.attribute_value_json)
  const notFound = isNotFoundValue(fact.attribute_value)
  const hasContradiction = fact.contradicts_fact_id != null

  return (
    <div className={`border-l-4 ${confidenceBorder(fact.confidence)} bg-[#f5f0e8] rounded-r-md p-3 space-y-1`}>
      {/* Question + review controls */}
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-sm font-medium text-[#2c2417]">
          {hasContradiction && (
            <AlertTriangle className="inline h-3.5 w-3.5 text-[#c78c4e] mr-1" title="Contradicts another fact" />
          )}
          {question}
        </h4>
        <div className="shrink-0 flex items-center gap-0.5">
          {fact.human_verdict ? (
            <span className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded border ${VERDICT_BADGE[fact.human_verdict]?.className || ''}`}>
              {VERDICT_BADGE[fact.human_verdict]?.label || fact.human_verdict}
            </span>
          ) : onReview ? (
            <span className="inline-flex items-center gap-0.5 relative">
              <button
                onClick={() => onReview(fact.fact_id, 'rejected', 'flag')}
                className="p-0.5 rounded hover:bg-[#c23a22]/10 text-[#8a7e6d] hover:text-[#c23a22] transition-colors"
                title="Flag as wrong"
                aria-label="Flag"
              >
                <Flag className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={(e) => {
                  const menu = e.currentTarget.nextElementSibling
                  if (menu) menu.classList.toggle('hidden')
                }}
                className="p-0.5 rounded hover:bg-muted text-[#8a7e6d] hover:text-[#5a5046] transition-colors"
                title="More review options"
                aria-label="More options"
              >
                <MoreHorizontal className="h-3.5 w-3.5" />
              </button>
              <span className="hidden absolute right-0 top-full mt-0.5 z-10 bg-card border rounded shadow-md p-1 flex gap-0.5">
                <button
                  onClick={() => onReview(fact.fact_id, 'confirmed')}
                  className="p-1 rounded hover:bg-[#3a7d44]/10 text-[#8a7e6d] hover:text-[#3a7d44] transition-colors"
                  title="Confirm fact"
                  aria-label="Confirm"
                >
                  <ThumbsUp className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => onReview(fact.fact_id, 'rejected')}
                  className="p-1 rounded hover:bg-[#c23a22]/10 text-[#8a7e6d] hover:text-[#c23a22] transition-colors"
                  title="Reject fact"
                  aria-label="Reject"
                >
                  <ThumbsDown className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => onReview(fact.fact_id, 'irrelevant')}
                  className="p-1 rounded hover:bg-[#8a7e6d]/10 text-[#8a7e6d] hover:text-[#5a5046] transition-colors"
                  title="Mark irrelevant"
                  aria-label="Irrelevant"
                >
                  <Minus className="h-3.5 w-3.5" />
                </button>
              </span>
            </span>
          ) : null}
        </div>
      </div>

      {/* Answer */}
      {notFound ? (
        <p className="text-sm text-[#8a7e6d] italic">No data found.</p>
      ) : (
        <div className="text-sm text-[#2c2417]">
          {typeof value === 'string' && value.length > 200 ? (
            <p className="whitespace-pre-wrap">{value}</p>
          ) : (
            <p>{value}</p>
          )}
        </div>
      )}

      {/* Source attribution footer - only show when data was found */}
      {!notFound && (
        <div className="flex items-center gap-2 text-[11px] text-[#8a7e6d]">
          {fact.source_name && (
            <span>Source: <span className="font-medium">{fact.source_name}</span></span>
          )}
          {fact.confidence != null && (
            <span className="flex items-center gap-1">
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${
                fact.confidence >= 0.7 ? 'bg-[#3a7d44]' :
                fact.confidence >= 0.4 ? 'bg-[#c78c4e]' : 'bg-[#d9cebb]'
              }`} />
              {fact.confidence.toFixed(2)}
            </span>
          )}
          {fact.as_of_date && <span>as of {fact.as_of_date}</span>}
        </div>
      )}
    </div>
  )
}
