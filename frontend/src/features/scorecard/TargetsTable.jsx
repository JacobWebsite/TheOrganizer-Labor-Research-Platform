import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
} from '@tanstack/react-table'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { QualityIndicator } from './QualityIndicator'

const PAGE_SIZE = 50

const SOURCE_STYLES = {
  sam:     'bg-amber-600 text-white',
  bmf:     'bg-teal-600 text-white',
  mergent: 'bg-indigo-600 text-white',
  f7:      'bg-stone-800 text-white',
}

function SourceBadge({ source }) {
  const style = SOURCE_STYLES[source] || 'bg-muted text-muted-foreground'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-xs font-semibold uppercase ${style}`}>
      {source}
    </span>
  )
}

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

/**
 * Targets table with TanStack Table: employer name, location, employees,
 * source origin, quality indicator, flag badges. Row click navigates to profile.
 */
export function TargetsTable({ data, total, page, pages, onPageChange }) {
  const navigate = useNavigate()

  const columns = useMemo(() => [
    {
      accessorKey: 'display_name',
      header: 'Employer',
      cell: ({ getValue }) => (
        <div className="font-medium truncate max-w-[280px]">{getValue() || '\u2014'}</div>
      ),
    },
    {
      accessorKey: 'city',
      header: 'City',
      cell: ({ getValue }) => getValue() || '\u2014',
    },
    {
      accessorKey: 'state',
      header: 'State',
      cell: ({ getValue }) => getValue() || '\u2014',
    },
    {
      id: 'employees',
      header: () => <div className="text-right">Employees</div>,
      accessorKey: 'employee_count',
      cell: ({ getValue }) => (
        <div className="text-right tabular-nums">{formatNumber(getValue())}</div>
      ),
    },
    {
      accessorKey: 'source_origin',
      header: 'Source',
      cell: ({ getValue }) => <SourceBadge source={getValue()} />,
    },
    {
      id: 'sources',
      header: 'Sources',
      accessorKey: 'source_count',
      cell: ({ getValue }) => {
        const c = getValue()
        return <span className="text-xs text-muted-foreground">{c} source{c !== 1 ? 's' : ''}</span>
      },
    },
    {
      id: 'quality',
      header: 'Quality',
      accessorKey: 'data_quality_score',
      cell: ({ getValue }) => <QualityIndicator score={getValue()} />,
    },
    {
      id: 'flags',
      header: 'Flags',
      cell: ({ row }) => {
        const badges = []
        if (row.original.is_federal_contractor) badges.push('Fed Contractor')
        if (row.original.is_nonprofit) badges.push('Nonprofit')
        if (badges.length === 0) return null
        return (
          <div className="flex gap-1">
            {badges.map((b) => (
              <span key={b} className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium border bg-muted">
                {b}
              </span>
            ))}
          </div>
        )
      },
    },
  ], [])

  const table = useReactTable({
    data: data || [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    pageCount: pages || 1,
  })

  const startRow = (page - 1) * PAGE_SIZE + 1
  const endRow = Math.min(page * PAGE_SIZE, total || 0)

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto border">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b bg-muted/50">
                {hg.headers.map((header) => (
                  <th key={header.id} className="px-3 py-2 text-left font-medium text-muted-foreground">
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className="border-b hover:bg-accent/50 cursor-pointer transition-colors"
                onClick={() => navigate(`/employers/MASTER-${row.original.id}`)}
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
              Page {page} of {pages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= pages}
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
