import { cn } from '@/lib/utils'

const SOURCE_STYLES = {
  F7:     'bg-[#2c2418] text-[#faf6ef]',
  OSHA:   'bg-[#c23a22] text-white',
  NLRB:   'bg-[#3a6b8c] text-white',
  WHD:    'bg-[#8b5e3c] text-white',
  SAM:    'bg-[#1a6b5a] text-white',
  SEC:    'bg-[#6b5b8a] text-white',
  GLEIF:  'bg-[#ede7db] text-[#2c2418] border border-[#d9cebb]',
  BMF:    'bg-[#c78c4e] text-white',
  VR:     'bg-[#3a7d44] text-white',
  MANUAL: 'bg-[#6b5b8a] text-white',
}

export function SourceBadge({ source }) {
  const style = SOURCE_STYLES[source] || 'bg-muted text-muted-foreground'
  return (
    <span className={cn('inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold', style)}>
      {source}
    </span>
  )
}
