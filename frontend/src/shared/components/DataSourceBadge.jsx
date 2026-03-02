import { cn } from '@/lib/utils'
import { Check, Minus, X } from 'lucide-react'

function getSourceState(hasFlag, hasData) {
  if (hasFlag && hasData) return 'present'
  if (hasFlag) return 'no_records'
  return 'not_matched'
}

const STATE_CONFIG = {
  present: {
    label: 'Matched',
    icon: Check,
    className: 'bg-[#3a7d44]/15 text-[#3a7d44] border-[#3a7d44]/30',
  },
  no_records: {
    label: 'No Records',
    icon: Minus,
    className: 'bg-[#8a7e6b]/15 text-[#8a7e6b] border-[#8a7e6b]/30',
  },
  not_matched: {
    label: 'Not Matched',
    icon: X,
    className: 'bg-amber-100 text-amber-800 border-amber-300',
  },
}

export function DataSourceBadge({ source, hasFlag, hasData }) {
  const state = getSourceState(hasFlag, hasData)
  const config = STATE_CONFIG[state]
  const Icon = config.icon

  return (
    <span className={cn('inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs font-medium', config.className)}>
      <Icon className="h-3 w-3" />
      {source}: {config.label}
    </span>
  )
}
