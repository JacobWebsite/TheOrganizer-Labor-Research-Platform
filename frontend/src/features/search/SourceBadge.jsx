import { cn } from '@/lib/utils'

const SOURCE_STYLES = {
  F7:     'bg-stone-800 text-white',
  OSHA:   'bg-stone-700 text-white',
  NLRB:   'bg-stone-600 text-white',
  WHD:    'bg-stone-600 text-white',
  SAM:    'bg-stone-500 text-white',
  SEC:    'bg-stone-500 text-white',
  GLEIF:  'bg-stone-100 text-stone-700 border border-stone-300',
  BMF:    'bg-stone-100 text-stone-700 border border-stone-300',
  VR:     'bg-green-600 text-white',
  MANUAL: 'bg-purple-600 text-white',
}

export function SourceBadge({ source }) {
  const style = SOURCE_STYLES[source] || 'bg-muted text-muted-foreground'
  return (
    <span className={cn('inline-flex items-center px-2 py-0.5 text-xs font-semibold', style)}>
      {source}
    </span>
  )
}
