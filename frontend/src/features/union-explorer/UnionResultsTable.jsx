import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
} from '@tanstack/react-table'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

const PAGE_SIZE = 50

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

/**
 * TanStack Table for union search results with server-side pagination.
 */
export function UnionResultsTable({ data, total, page, onPageChange }) {
  const navigate = useNavigate()
  const pages = Math.ceil((total || 0) / PAGE_SIZE)

  const columns = useMemo(() => [
    {
      id: 'name',
      header: 'Union Name',
      accessorFn: (row) => row.display_name || row.union_name,
      cell: ({ getValue }) => (
        <div className="font-medium truncate max-w-[320px]">{getValue() || '\u2014'}</div>
      ),
    },
    {
      accessorKey: 'aff_abbr',
      header: 'Affiliation',
      cell: ({ getValue }) => {
        const v = getValue()
        if (!v) return '\u2014'
        return <Badge variant="secondary">{v}</Badge>
      },
    },
    {
      id: 'location',
      header: 'City/State',
      cell: ({ row }) => {
        const city = row.original.city
        const state = row.original.state
        if (!city && !state) return '\u2014'
        return [city, state].filter(Boolean).join(', ')
      },
    },
    {
      id: 'members',
      header: () => <div className="text-right" title="Dues-paying members (LM filings)">Members</div>,
      accessorKey: 'members',
      cell: ({ getValue }) => (
        <div className="text-right tabular-nums">{formatNumber(getValue())}</div>
      ),
    },
    {
      id: 'employers',
      header: () => <div className="text-right">Employers</div>,
      accessorKey: 'f7_employer_count',
      cell: ({ getValue }) => (
        <div className="text-right tabular-nums">{formatNumber(getValue())}</div>
      ),
    },
    {
      id: 'workers',
      header: () => <div className="text-right" title="Workers covered by bargaining agreements (F-7 filings)">Covered</div>,
      accessorKey: 'f7_total_workers',
      cell: ({ getValue }) => (
        <div className="text-right tabular-nums">{formatNumber(getValue())}</div>
      ),
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
                onClick={() => navigate(`/unions/${row.original.f_num}`)}
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
