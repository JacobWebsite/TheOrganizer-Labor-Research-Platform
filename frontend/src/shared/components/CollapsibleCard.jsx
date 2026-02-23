import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

export function CollapsibleCard({ icon: Icon, title, summary, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <Card>
      <CardHeader
        className="cursor-pointer select-none"
        onClick={() => setOpen((v) => !v)}
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
