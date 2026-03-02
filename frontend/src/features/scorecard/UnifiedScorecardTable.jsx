import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
} from '@tanstack/react-table'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 50

const TIER_COLORS = {
  Priority: '#c23a22',
  Strong: '#1a6b5a',
  Promising: '#c78c4e',
  Moderate: '#8a7e6b',
  Low: '#d9cebb',
}

function TierBadge({ tier }) {
  if (!tier) return <span className="text-xs text-muted-foreground">--</span>
  const color = TIER_COLORS[tier] || '#8a7e6b'
  const isLight = tier === 'Low'
  return (
    <span
      className="inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-bold uppercase"
      style={{
        backgroundColor: color,
        color: isLight ? '#2c2418' : '#faf6ef',
      }}
    >
      {tier}
    </span>
  )
}

function ScoreCell({ score, tier }) {
  if (score == null) return <span className="text-xs text-muted-foreground">--</span>
  const color = TIER_COLORS[tier] || '#8a7e6b'
  return (
    <span className="font-semibold tabular-nums" style={{ color }}>
      {Number(score).toFixed(1)}
    </span>
  )
}

function FactorsBadge({ factors, total }) {
  if (factors == null) return <span className="text-xs text-muted-foreground">--</span>
  if (factors < 3) {
    return (
      <span className="rounded-md px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-800 border border-amber-300">
        {factors}/{total} - Low Data
      </span>
    )
  }
  return (
    <span className={cn(
      'rounded-md px-2 py-0.5 text-xs font-medium',
      factors >= 5 ? 'bg-[#1a6b5a]/20 text-[#1a6b5a]' : 'bg-[#c78c4e]/20 text-[#c78c4e]'
    )}>
      {factors}/{total}
    </span>
  )
}

function SubScore({ value }) {
  if (value == null) return <span className="text-xs text-muted-foreground">--</span>
  return <span className="tabular-nums text-sm">{Number(value).toFixed(1)}</span>
}

function FlagBadges({ row }) {
  const badges = []
  if (row.has_compound_enforcement) badges.push({ key: 'compound', label: 'Compound', color: '#c23a22' })
  if (row.has_close_election) badges.push({ key: 'close', label: 'Close Elec.', color: '#c78c4e' })
  if (row.has_child_labor) badges.push({ key: 'child', label: 'Child Labor', color: '#c23a22' })
  if (row.is_whd_repeat_violator) badges.push({ key: 'repeat', label: 'Repeat WHD', color: '#8a7e6b' })
  if (badges.length === 0) return null
  return (
    <div className="flex flex-wrap gap-0.5">
      {badges.map((b) => (
        <span
          key={b.key}
          className="inline-flex items-center rounded px-1 py-0.5 text-[9px] font-bold border"
          style={{
            backgroundColor: `${b.color}15`,
            color: b.color,
            borderColor: `${b.color}30`,
          }}
        >
          {b.label}
        </span>
      ))}
    </div>
  )
}

/**
 * Unified scorecard table with TanStack Table: employer name, location, score,
 * tier, factors, sub-scores, action, flags. Row click navigates to employer profile.
 */
export function UnifiedScorecardTable({ data, total, offset, pageSize, onPageChange }) {
  const navigate = useNavigate()

  const page = Math.floor(offset / pageSize) + 1
  const pages = Math.ceil((total || 0) / pageSize)

  const columns = useMemo(() => [
    {
      id: 'rank',
      header: '#',
      cell: ({ row }) => (
        <div className="text-xs text-muted-foreground tabular-nums">{offset + row.index + 1}</div>
      ),
      size: 40,
    },
    {
      accessorKey: 'employer_name',
      header: 'Employer',
      cell: ({ getValue }) => (
        <div className="font-medium truncate max-w-[260px] text-[#1a6b5a] cursor-pointer">
          {getValue() || '--'}
        </div>
      ),
    },
    {
      id: 'location',
      header: 'Location',
      accessorFn: (row) => [row.city, row.state].filter(Boolean).join(', '),
      cell: ({ getValue }) => (
        <div className="text-sm truncate max-w-[140px]">{getValue() || '--'}</div>
      ),
    },
    {
      id: 'score',
      header: () => <div className="text-right">Score</div>,
      accessorKey: 'weighted_score',
      cell: ({ row }) => (
        <div className="text-right">
          <ScoreCell score={row.original.weighted_score} tier={row.original.score_tier} />
        </div>
      ),
    },
    {
      id: 'tier',
      header: 'Tier',
      accessorKey: 'score_tier',
      cell: ({ getValue }) => <TierBadge tier={getValue()} />,
    },
    {
      id: 'factors',
      header: () => <div className="text-center">Factors</div>,
      cell: ({ row }) => (
        <div className="text-center">
          <FactorsBadge factors={row.original.factors_available} total={row.original.factors_total} />
        </div>
      ),
    },
    {
      id: 'osha',
      header: () => <div className="text-center">OSHA</div>,
      cell: ({ row }) => <div className="text-center"><SubScore value={row.original.score_osha} /></div>,
    },
    {
      id: 'nlrb',
      header: () => <div className="text-center">NLRB</div>,
      cell: ({ row }) => <div className="text-center"><SubScore value={row.original.score_nlrb} /></div>,
    },
    {
      id: 'whd',
      header: () => <div className="text-center">WHD</div>,
      cell: ({ row }) => <div className="text-center"><SubScore value={row.original.score_whd} /></div>,
    },
    {
      id: 'action',
      header: 'Action',
      accessorKey: 'recommended_action',
      cell: ({ getValue }) => {
        const val = getValue()
        if (!val) return <span className="text-xs text-muted-foreground">--</span>
        return <span className="text-xs font-medium">{val}</span>
      },
    },
    {
      id: 'flags',
      header: 'Flags',
      cell: ({ row }) => <FlagBadges row={row.original} />,
    },
  ], [offset])

  const table = useReactTable({
    data: data || [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    pageCount: pages || 1,
  })

  const startRow = offset + 1
  const endRow = Math.min(offset + pageSize, total || 0)

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto border rounded-lg">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b bg-[#ede7db]">
                {hg.headers.map((header) => (
                  <th key={header.id} className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row, i) => (
              <tr
                key={row.id}
                className={cn(
                  'border-b hover:bg-accent/50 cursor-pointer transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary',
                  i % 2 === 1 ? 'bg-[#f5f0e8]/50' : ''
                )}
                tabIndex={0}
                onClick={() => navigate(`/employers/${row.original.employer_id}`)}
                onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/employers/${row.original.employer_id}`) }}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-2">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total > pageSize && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Showing {startRow}&ndash;{endRow} of {total.toLocaleString()}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(offset - pageSize)}
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {page} of {pages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= pages}
              onClick={() => onPageChange(offset + pageSize)}
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
