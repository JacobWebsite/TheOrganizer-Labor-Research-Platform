import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
} from '@tanstack/react-table'
import { ArrowUpDown, ChevronLeft, ChevronRight, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { SourceBadge } from './SourceBadge'

const PAGE_SIZE = 25

// Aged Broadsheet tier colors (keep in sync with ProfileHeader + TargetsPage).
const TIER_COLORS = {
  Priority: '#c23a22',
  Strong: '#1a6b5a',
  Promising: '#c78c4e',
  Moderate: '#8a7e6b',
  Low: '#d9cebb',
  // Speculative (added 2026-05-06): muted gray-blue. Distinct from Low
  // (which has real enforcement) to signal "modeled, unverified."
  Speculative: '#7a8b9a',
}

function ScoreCell({ score, tier, thin }) {
  if (score == null) {
    return <span className="text-muted-foreground">{'\u2014'}</span>
  }
  const color = TIER_COLORS[tier] || '#8a7e6b'
  const isLight = tier === 'Low'
  return (
    <div className="flex items-center gap-1.5 whitespace-nowrap">
      <span className="font-semibold tabular-nums" style={{ color }}>
        {Number(score).toFixed(1)}
      </span>
      {tier && (
        <span
          className="inline-flex items-center rounded-sm px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide"
          style={{
            backgroundColor: color,
            color: isLight ? '#2c2418' : '#faf6ef',
          }}
        >
          {tier}
        </span>
      )}
      {thin && (
        <span
          className="inline-flex items-center gap-0.5 rounded-sm border border-amber-300 bg-amber-100 px-1 py-0.5 text-[9px] font-medium text-amber-800"
          title="Score built from modeled signals only"
        >
          <AlertTriangle className="h-2.5 w-2.5" />
          thin
        </span>
      )}
    </div>
  )
}

function SortHeader({ column, children }) {
  return (
    <button
      type="button"
      className="inline-flex items-center gap-1 hover:text-foreground"
      onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
    >
      {children}
      <ArrowUpDown className="h-3 w-3" />
    </button>
  )
}

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

/**
 * Results table with TanStack Table -- sortable columns, pagination, row click navigation.
 */
export function ResultsTable({ data, total, page, onPageChange }) {
  const navigate = useNavigate()

  const columns = useMemo(() => [
    {
      accessorKey: 'employer_name',
      header: ({ column }) => <SortHeader column={column}>Employer</SortHeader>,
      cell: ({ row }) => {
        const name = row.original.employer_name
        const groupCount = row.original.group_member_count
        return (
          <div className="font-medium">
            {name}
            {groupCount > 1 && (
              <span className="ml-1.5 text-xs text-muted-foreground">
                ({groupCount} locations)
              </span>
            )}
          </div>
        )
      },
    },
    {
      id: 'score',
      header: ({ column }) => <SortHeader column={column}>Score</SortHeader>,
      accessorFn: (row) => row.weighted_score,
      cell: ({ row }) => (
        <ScoreCell
          score={row.original.weighted_score}
          tier={row.original.score_tier}
          thin={row.original.has_thin_data}
        />
      ),
    },
    {
      accessorKey: 'city',
      header: 'City',
      cell: ({ getValue }) => getValue() || '\u2014',
    },
    {
      accessorKey: 'state',
      header: ({ column }) => <SortHeader column={column}>State</SortHeader>,
      cell: ({ getValue }) => getValue() || '\u2014',
    },
    {
      id: 'industry',
      header: 'Industry',
      accessorFn: (row) => row.naics_description || row.sector_name,
      cell: ({ getValue, row }) => {
        const desc = getValue()
        const code = row.original.naics_code || row.original.naics_2digit
        if (!desc && !code) return <span className="text-muted-foreground">{'\u2014'}</span>
        return (
          <span className="truncate max-w-[180px] inline-block" title={desc || ''}>
            {code ? `${code} ` : ''}{desc || ''}
          </span>
        )
      },
    },
    {
      id: 'workers',
      header: ({ column }) => (
        <div className="text-right">
          <SortHeader column={column}>Workers</SortHeader>
        </div>
      ),
      accessorFn: (row) => row.consolidated_workers || row.unit_size,
      cell: ({ getValue }) => (
        <div className="text-right">{formatNumber(getValue())}</div>
      ),
    },
    {
      accessorKey: 'source_type',
      header: 'Source',
      cell: ({ getValue }) => <SourceBadge source={getValue()} />,
    },
    {
      accessorKey: 'union_name',
      header: 'Union',
      cell: ({ getValue }) => {
        const v = getValue()
        if (!v) return <span className="text-muted-foreground">{'\u2014'}</span>
        return <span className="truncate max-w-[200px] inline-block">{v}</span>
      },
    },
  ], [])

  const table = useReactTable({
    data: data || [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    pageCount: Math.ceil((total || 0) / PAGE_SIZE),
  })

  const totalPages = Math.ceil((total || 0) / PAGE_SIZE)
  const startRow = (page - 1) * PAGE_SIZE + 1
  const endRow = Math.min(page * PAGE_SIZE, total || 0)

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
                  'border-b hover:bg-accent/50 cursor-pointer transition-colors',
                  i % 2 === 1 && 'bg-[#f5f0e8]/50'
                )}
                onClick={() => navigate(`/employers/${row.original.canonical_id}`)}
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
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Showing {startRow}&ndash;{endRow} of {total.toLocaleString()}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
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
