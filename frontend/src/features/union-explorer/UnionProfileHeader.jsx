import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { MiniStat } from '@/shared/components/MiniStat'

/**
 * Hero banner for union profile page — teal gradient with key stats.
 */
export function UnionProfileHeader({ union, employers }) {
  if (!union) return null

  const affPath = [union.aff_abbr, union.sector].filter(Boolean).join(' > ')
  const winRate = union.election_win_rate != null
    ? `${Math.round(union.election_win_rate * 100)}%`
    : null

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
        <h1 className="font-editorial text-[28px] font-bold text-white leading-tight">
          {union.union_name || '\u2014'}
        </h1>

        <div className="flex flex-wrap gap-8 mt-4">
          {union.members != null && (
            <div>
              <p className="text-2xl font-bold text-white">{Number(union.members).toLocaleString()}</p>
              <p className="text-xs text-white/70">Members</p>
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
          label="Total Workers"
          value={union.total_workers != null ? Number(union.total_workers).toLocaleString() : '--'}
          accent="#1a6b5a"
        />
      </div>
    </div>
  )
}
