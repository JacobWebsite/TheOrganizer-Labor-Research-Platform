import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ChevronDown, ChevronRight, FileText, Building2, Users, Calendar } from 'lucide-react'
import { useCBAArticles } from '@/shared/api/cba'
import { cn } from '@/lib/utils'

const CATEGORY_COLORS = {
  union_security: 'bg-purple-100 text-purple-800',
  coverage: 'bg-gray-100 text-gray-800',
  wages_hours: 'bg-green-100 text-green-800',
  management_rights: 'bg-red-100 text-red-800',
  grievance: 'bg-orange-100 text-orange-800',
  arbitration: 'bg-orange-100 text-orange-800',
  job_security: 'bg-blue-100 text-blue-800',
  no_strike: 'bg-red-100 text-red-700',
  signatory: 'bg-gray-100 text-gray-700',
  benefits: 'bg-teal-100 text-teal-800',
  disability: 'bg-teal-100 text-teal-700',
  sick_leave: 'bg-teal-100 text-teal-700',
  leave: 'bg-cyan-100 text-cyan-800',
  classifications: 'bg-gray-100 text-gray-700',
  superintendents: 'bg-amber-100 text-amber-800',
  new_development: 'bg-indigo-100 text-indigo-800',
  joint_industry: 'bg-indigo-100 text-indigo-700',
  general: 'bg-gray-100 text-gray-600',
  duration: 'bg-yellow-100 text-yellow-800',
  building_acquisition: 'bg-gray-100 text-gray-700',
  safety: 'bg-red-100 text-red-700',
  technology: 'bg-violet-100 text-violet-800',
  other: 'bg-gray-100 text-gray-600',
}

const SUBFIELD_LABELS = {
  contract_term_years: 'Term',
  holiday_count: 'Holidays',
  holiday_pay_rate: 'Holiday pay',
  overtime_rate_multiplier: 'OT rate',
  grievance_step_count: 'Steps',
  has_no_strike_clause: 'No-strike',
  probationary_period: 'Probation',
}

function SubfieldBar({ subfields }) {
  if (!subfields || Object.keys(subfields).length === 0) return null

  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 pb-2 text-xs text-[#5a5347]">
      {Object.entries(subfields).map(([key, data]) => (
        <span key={key}>
          <span className="text-[#8a7e6d]">{SUBFIELD_LABELS[key] || key}:</span>{' '}
          <span className="font-medium">{data.display}</span>
        </span>
      ))}
    </div>
  )
}

function ArticleCard({ article }) {
  const [open, setOpen] = useState(false)
  const colorCls = CATEGORY_COLORS[article.category] || CATEGORY_COLORS.other
  const hasSubfields = article.subfields && Object.keys(article.subfields).length > 0

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-muted/20 transition-colors"
      >
        {open
          ? <ChevronDown className="h-4 w-4 shrink-0 text-[#8a7e6d]" />
          : <ChevronRight className="h-4 w-4 shrink-0 text-[#8a7e6d]" />
        }
        <span className="font-mono text-sm text-[#8a7e6d] shrink-0 w-12">
          Art {article.number}
        </span>
        <span className="font-medium text-sm flex-1">{article.title}</span>
        <span className={cn('text-xs px-2 py-0.5 rounded-full shrink-0', colorCls)}>
          {article.category.replace(/_/g, ' ')}
        </span>
        <span className="text-xs text-[#8a7e6d] shrink-0">
          {article.word_count?.toLocaleString()} words
        </span>
      </button>

      {hasSubfields && <SubfieldBar subfields={article.subfields} />}

      {open && (
        <div className="border-t bg-muted/5">
          {hasSubfields && (
            <div className="px-4 pt-3 pb-2 border-b border-dashed">
              <div className="text-xs font-medium text-[#8a7e6d] mb-1.5">Key Terms</div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
                {Object.entries(article.subfields).map(([key, data]) => (
                  <div key={key} className="flex justify-between">
                    <span className="text-[#8a7e6d]">{SUBFIELD_LABELS[key] || key}</span>
                    <span className="font-medium">{data.display}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="text-sm leading-relaxed whitespace-normal break-words w-full p-4">
            {article.text}
          </div>
          {article.page_start && (
            <div className="px-4 pb-3 text-xs text-[#8a7e6d]">
              Pages {article.page_start}{article.page_end && article.page_end !== article.page_start ? `--${article.page_end}` : ''}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function CBAArticles() {
  const { cbaId } = useParams()
  const { data, isLoading, isError, error } = useCBAArticles(cbaId)

  useEffect(() => { document.title = 'Contract Articles - The Organizer' }, [])

  if (isLoading) {
    return <div className="py-12 text-center text-[#8a7e6d]">Loading contract...</div>
  }
  if (isError) {
    return (
      <div className="py-12 text-center text-destructive">
        Failed to load: {error?.message || 'Unknown error'}
      </div>
    )
  }

  const doc = data?.document
  const articles = data?.articles || []

  return (
    <div className="space-y-4">
      {/* Back link */}
      <Link to="/cbas" className="text-sm text-[#c78c4e] hover:underline">
        &larr; All contracts
      </Link>

      {/* Contract header */}
      <div className="border rounded-lg p-5 space-y-3">
        <h1 className="font-editorial text-2xl font-bold">
          {doc?.employer_name_raw || 'Unknown Employer'}
        </h1>

        <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-[#8a7e6d]">
          <span className="flex items-center gap-1.5">
            <Building2 className="h-4 w-4" />
            {doc?.employer_name_raw || 'Unknown'}
          </span>
          <span className="flex items-center gap-1.5">
            <Users className="h-4 w-4" />
            {doc?.union_name_raw || 'Unknown'}{doc?.local_number ? ` Local ${doc.local_number}` : ''}
          </span>
          {(doc?.effective_date || doc?.expiration_date) && (
            <span className="flex items-center gap-1.5">
              <Calendar className="h-4 w-4" />
              {doc?.effective_date || '?'} to {doc?.expiration_date || '?'}
            </span>
          )}
          <span className="flex items-center gap-1.5">
            <FileText className="h-4 w-4" />
            {doc?.page_count || '?'} pages
          </span>
        </div>

        <div className="flex items-center justify-between">
          <div className="text-sm">
            <span className="font-medium">{articles.length}</span> articles
            <span className="text-[#8a7e6d]"> -- click any article to expand full text</span>
          </div>
          <Link to={`/cbas/${cbaId}`} className="text-sm text-[#c78c4e] hover:underline">
            View provisions
          </Link>
        </div>
      </div>

      {/* Article list */}
      <div className="space-y-2">
        {articles.map(a => (
          <ArticleCard key={a.section_id || a.number} article={a} />
        ))}
      </div>

      {articles.length === 0 && (
        <div className="py-12 text-center text-[#8a7e6d]">
          No articles extracted yet. Run <code className="font-mono text-xs">extract_articles.py --cba-id {cbaId}</code> first.
        </div>
      )}
    </div>
  )
}
