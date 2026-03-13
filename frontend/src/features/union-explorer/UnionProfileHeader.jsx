import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { MiniStat } from '@/shared/components/MiniStat'

/**
 * Hero banner for union profile page — teal gradient with key stats.
 */
const GRADE_COLORS = { A: '#1a6b5a', B: '#4a90a4', C: '#c78c4e', D: '#b8860b', F: '#a0522d' }

export function UnionProfileHeader({ union, employers, healthGrade }) {
  if (!union) return null

  const affPath = [union.aff_abbr, union.sector].filter(Boolean).join(' > ')
  const winRate = union.election_win_rate != null
    ? `${Math.round(union.election_win_rate * 100)}%`
    : null
  const coveredWorkers = union.f7_total_workers
  const lmMembers = union.members
  // Flag extreme ratio (>10x) between covered workers and dues-paying members
  const workerMemberRatio = (coveredWorkers > 0 && lmMembers > 0) ? coveredWorkers / lmMembers : null
  const hasExtremeRatio = workerMemberRatio != null && workerMemberRatio > 10

  return (
    <div className="space-y-3">
      <Link
        to="/unions"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Unions
      </Link>

      {/* Teal gradient hero */}
      <div
        className="rounded-lg px-6 py-5"
        style={{ background: 'linear-gradient(135deg, #1a6b5a 0%, #2a8a74 100%)' }}
      >
        {affPath && (
          <p className="text-xs uppercase tracking-wider text-white/70 mb-1">{affPath}</p>
        )}
        <div className="flex items-center gap-3">
          <h1 className="font-editorial text-[28px] font-bold text-white leading-tight">
            {union.union_name || '\u2014'}
            {union.local_number && union.local_number !== '0' && (
              <span className="text-xl font-normal text-white/80 ml-2">Local {union.local_number}</span>
            )}
          </h1>
          {healthGrade && (
            <span
              className="inline-flex items-center justify-center w-8 h-8 rounded-full text-white font-bold text-sm shrink-0"
              style={{ backgroundColor: GRADE_COLORS[healthGrade] || '#8a7e6d' }}
              title={`Health grade: ${healthGrade}`}
            >
              {healthGrade}
            </span>
          )}
        </div>

        <div className="flex flex-wrap gap-8 mt-4">
          {lmMembers != null && (
            <div title="Dues-paying members reported on LM filings">
              <p className="text-2xl font-bold text-white">{Number(lmMembers).toLocaleString()}</p>
              <p className="text-xs text-white/70">Members <span className="text-white/40">(LM)</span></p>
            </div>
          )}
          {coveredWorkers != null && coveredWorkers > 0 && (
            <div title="Workers covered by collective bargaining agreements (F-7 filings) -- may exceed dues-paying members">
              <p className="text-2xl font-bold text-white">{Number(coveredWorkers).toLocaleString()}</p>
              <p className="text-xs text-white/70">Covered Workers <span className="text-white/40">(F-7)</span></p>
            </div>
          )}
          {winRate && (
            <div>
              <p className="text-2xl font-bold text-white">{winRate}</p>
              <p className="text-xs text-white/70">Election Win Rate</p>
            </div>
          )}
          {union.states_active != null && (
            <div>
              <p className="text-2xl font-bold text-white">{union.states_active}</p>
              <p className="text-xs text-white/70">States Active</p>
            </div>
          )}
          {union.local_count != null && (
            <div>
              <p className="text-2xl font-bold text-white">{union.local_count}</p>
              <p className="text-xs text-white/70">Locals</p>
            </div>
          )}
        </div>
      </div>

      {/* MiniStat row */}
      <div className="flex gap-3">
        <MiniStat
          label="Recent Elections"
          value={union.recent_elections ?? '--'}
          accent="#4a90a4"
        />
        <MiniStat
          label="Employers"
          value={union.employer_count != null ? Number(union.employer_count).toLocaleString() : (employers?.length ?? '--')}
          accent="#c78c4e"
        />
        <MiniStat
          label="Covered Workers (F-7)"
          value={coveredWorkers != null && coveredWorkers > 0 ? Number(coveredWorkers).toLocaleString() : '--'}
          accent="#1a6b5a"
        />
      </div>
      {hasExtremeRatio && (
        <p className="text-xs text-muted-foreground italic">
          Covered workers ({Math.round(workerMemberRatio)}x members) -- F-7 counts all workers in bargaining units, while LM counts dues-paying members only. This ratio is common in building trades and public sector unions.
        </p>
      )}
    </div>
  )
}
