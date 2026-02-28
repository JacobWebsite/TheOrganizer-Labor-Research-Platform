import { useState, useCallback } from 'react'
import { ChevronDown } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

function usePersistedState(storageKey, defaultOpen) {
  const [isOpen, setIsOpen] = useState(() => {
    if (!storageKey) return defaultOpen
    try {
      const saved = localStorage.getItem(storageKey)
      return saved !== null ? saved === 'true' : defaultOpen
    } catch {
      return defaultOpen
    }
  })

  const toggle = useCallback(() => {
    setIsOpen((prev) => {
      const next = !prev
      if (storageKey) {
        try { localStorage.setItem(storageKey, String(next)) } catch {}
      }
      return next
    })
  }, [storageKey])

  return [isOpen, toggle]
}

export function CollapsibleCard({ icon: Icon, title, summary, defaultOpen = false, storageKey, children }) {
  const [open, toggle] = usePersistedState(storageKey, defaultOpen)

  return (
    <Card>
      <CardHeader
        className="cursor-pointer select-none"
        onClick={toggle}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {Icon && <Icon className="h-5 w-5 text-muted-foreground" />}
            <CardTitle>{title}</CardTitle>
          </div>
          <div className="flex items-center gap-3">
            {!open && summary && (
              <span className="text-sm text-muted-foreground">{summary}</span>
            )}
            <ChevronDown className={cn('h-4 w-4 text-muted-foreground transition-transform', open && 'rotate-180')} />
          </div>
        </div>
      </CardHeader>
      {open && <CardContent>{children}</CardContent>}
    </Card>
  )
}
