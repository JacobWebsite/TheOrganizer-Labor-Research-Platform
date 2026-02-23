import { Target } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Button } from '@/components/ui/button'

export function ExpansionTargetsSection({ union, employers }) {
  const navigate = useNavigate()

  // Extract primary state and NAICS from the union's employers
  const stateFreq = {}
  const naicsFreq = {}
  for (const emp of (employers || [])) {
    if (emp.state) stateFreq[emp.state] = (stateFreq[emp.state] || 0) + 1
    const naics2 = (emp.naics || emp.naics_code || '').slice(0, 2)
    if (naics2) naicsFreq[naics2] = (naicsFreq[naics2] || 0) + 1
  }

  const topStates = Object.entries(stateFreq).sort((a, b) => b[1] - a[1]).slice(0, 3)
  const topNaics = Object.entries(naicsFreq).sort((a, b) => b[1] - a[1]).slice(0, 2)
  const primaryState = topStates[0]?.[0]
  const primaryNaics = topNaics[0]?.[0]

  if (!primaryState && !primaryNaics) return null

  const summary = primaryState ? `Expansion opportunities in ${primaryState}` : 'Expansion opportunities'

  const buildTargetUrl = () => {
    const params = new URLSearchParams()
    if (primaryNaics) params.set('naics', primaryNaics)
    if (primaryState) params.set('state', primaryState)
    return `/targets?${params}`
  }

  return (
    <CollapsibleCard icon={Target} title="Expansion Targets" summary={summary}>
      <div className="space-y-4">
        <div className="text-sm">
          <p className="text-muted-foreground mb-2">
            Based on {union?.union_name || 'this union'}'s current employer base:
          </p>
          <div className="grid grid-cols-2 gap-4">
            {topStates.length > 0 && (
              <div>
                <span className="text-muted-foreground">Primary States</span>
                <div className="font-medium">{topStates.map(([s]) => s).join(', ')}</div>
              </div>
            )}
            {topNaics.length > 0 && (
              <div>
                <span className="text-muted-foreground">Primary Industries</span>
                <div className="font-medium">NAICS {topNaics.map(([n]) => n).join(', ')}</div>
              </div>
            )}
          </div>
        </div>

        <Button
          variant="outline"
          className="gap-1.5"
          onClick={() => navigate(buildTargetUrl())}
        >
          <Target className="h-4 w-4" />
          Browse non-union targets in {primaryState || 'these industries'}
        </Button>
      </div>
    </CollapsibleCard>
  )
}
