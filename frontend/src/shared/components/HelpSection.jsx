import { useState } from 'react'
import { HelpCircle, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

export function HelpSection({ children }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border-b">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-1 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <HelpCircle className="h-4 w-4" />
        <span>How to read this page</span>
        <ChevronDown className={cn('ml-auto h-4 w-4 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="pb-4 px-1 text-sm text-muted-foreground space-y-3">
          {children}
        </div>
      )}
    </div>
  )
}
