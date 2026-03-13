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
  sam:     'bg-[#1a6b5a] text-white',
  bmf:     'bg-[#c78c4e] text-white',
  mergent: 'bg-[#6b5b8a] text-white',
  f7:      'bg-[#2c2418] text-[#faf6ef]',
  osha:    'bg-[#c23a22] text-white',
  whd:     'bg-[#8b5e3c] text-white',
  nlrb:    'bg-[#3a6b8c] text-white',
  corpwatch: 'bg-[#6b5b8a] text-white',
}

const TIER_STYLES = {
  platinum: 'bg-gradient-to-r from-[#6b5b8a] to-[#8b7baa] text-white',
  gold:     'bg-gradient-to-r from-[#8B6914] to-[#c78c4e] text-white',
  silver:   'bg-gradient-to-r from-[#6b6b6b] to-[#8a8a8a] text-white',
  bronze:   'bg-[#8b5e3c] text-white',
  stub:     'bg-[#d9cebb] text-[#8a7e6b]',
}

function TierBadge({ tier }) {
  if (!tier || tier === 'stub') return null
  const style = TIER_STYLES[tier] || TIER_STYLES.stub
  return (
    <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase ${style}`}>
      {tier}
    </span>
  )
}

function SourceBadge({ source }) {
  const style = SOURCE_STYLES[source] || 'bg-muted text-muted-foreground'
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold uppercase ${style}`}>
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
export function TargetsTable({
  data,
  total,
  page,
  pages,
  onPageChange,
  selectedIds = [],
  onToggleSelect,
  onToggleSelectPage,
  maxSelected = 3,
}) {
  const navigate = useNavigate()
  const selectedSet = new Set(selectedIds)
  const pageIds = (data || []).map((row) => String(row.id))
  const allSelectedOnPage = pageIds.length > 0 && pageIds.every((id) => selectedSet.has(id))

  const columns = useMemo(() => [
    {
      id: 'select',
      header: () => (
        <input
          type="checkbox"
          aria-label="Select all employers on page"
          checked={allSelectedOnPage}
          onChange={(e) => onToggleSelectPage?.(data || [], e.target.checked)}
        />
      ),
      cell: ({ row }) => {
        const id = `MASTER-${row.original.id}`
        const checked = selectedSet.has(id)
        const disabled = !checked && selectedIds.length >= maxSelected
        return (
          <input
            type="checkbox"
            aria-label={`Select ${row.original.display_name}`}
            checked={checked}
            disabled={disabled}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => onToggleSelect?.(id, e.target.checked)}
          />
        )
      },
      size: 40,
    },
    {
      id: 'rank',
      header: '#',
      cell: ({ row }) => (
        <div className="text-xs text-muted-foreground tabular-nums">{(page - 1) * PAGE_SIZE + row.index + 1}</div>
      ),
      size: 40,
    },
    {
      accessorKey: 'display_name',
      header: 'Employer',
      cell: ({ getValue }) => (
        <div className="font-medium truncate max-w-[280px] text-[#1a6b5a] cursor-pointer">{getValue() || '\u2014'}</div>
      ),
    },
    {
      id: 'location',
      header: 'Location',
      accessorFn: (row) => [row.city, row.state].filter(Boolean).join(', '),
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
      id: 'signals',
      header: () => <div className="text-center">Signals</div>,
      accessorKey: 'signals_present',
      cell: ({ getValue }) => {
        const s = getValue()
        if (s == null) return <div className="text-center text-xs text-muted-foreground">--</div>
        return (
          <div className="text-center">
            <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-semibold ${
              s >= 4 ? 'bg-[#c23a22]/10 text-[#c23a22]' : s >= 2 ? 'bg-[#c78c4e]/15 text-[#c78c4e]' : 'bg-[#d9cebb]/50 text-[#8a7e6b]'
            }`}>
              {s}/9
            </span>
          </div>
        )
      },
    },
    {
      id: 'enforcement',
      header: () => <div className="text-center">Enforce.</div>,
      cell: ({ row }) => {
        const d = row.original
        if (!d.has_enforcement) return <div className="text-center text-xs text-muted-foreground">--</div>
        const icons = []
        if (d.signal_osha != null) icons.push('OSHA')
        if (d.signal_whd != null) icons.push('WHD')
        if (d.signal_nlrb != null) icons.push('NLRB')
        return (
          <div className="flex gap-0.5 justify-center">
            {icons.map(i => (
              <span key={i} className="inline-flex items-center rounded px-1 py-0.5 text-[9px] font-bold bg-[#c23a22]/10 text-[#c23a22]">
                {i}
              </span>
            ))}
          </div>
        )
      },
    },
    {
      id: 'quality',
      header: 'Quality',
      accessorKey: 'data_quality_score',
      cell: ({ getValue }) => <QualityIndicator score={getValue()} />,
    },
    {
      id: 'tier',
      header: 'Tier',
      accessorKey: 'gold_standard_tier',
      cell: ({ getValue }) => <TierBadge tier={getValue()} />,
    },
    {
      id: 'flags',
      header: 'Flags',
      cell: ({ row }) => {
        const badges = []
        if (row.original.is_federal_contractor) badges.push('Fed Contractor')
        if (row.original.is_nonprofit) badges.push('Nonprofit')
        if (row.original.is_low_wage_outlier) badges.push('Low Wage')
        if (badges.length === 0) return null
        return (
          <div className="flex gap-1">
            {badges.map((b) => (
              <span key={b} className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium border ${
                b === 'Low Wage' ? 'bg-[#c23a22]/10 text-[#c23a22] border-[#c23a22]/20' : 'bg-muted'
              }`}>
                {b}
              </span>
            ))}
          </div>
        )
      },
    },
  ], [allSelectedOnPage, data, maxSelected, onToggleSelect, onToggleSelectPage, page, selectedIds.length, selectedSet])

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
                className={`border-b hover:bg-accent/50 cursor-pointer transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${i % 2 === 1 ? 'bg-[#f5f0e8]/50' : ''}`}
                tabIndex={0}
                onClick={() => navigate(`/employers/MASTER-${row.original.id}`)}
                onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/employers/MASTER-${row.original.id}`) }}
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
