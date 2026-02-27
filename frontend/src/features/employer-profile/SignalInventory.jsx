import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card'
import { ShieldAlert, HandCoins, TrendingUp, Users } from 'lucide-react'
import { cn } from '@/lib/utils'

const SIGNAL_GROUPS = [
  {
    category: 'enforcement',
    label: 'Enforcement Signals',
    icon: ShieldAlert,
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
    signals: [
      { key: 'signal_osha', label: 'OSHA Safety' },
      { key: 'signal_whd', label: 'Wage & Hour' },
      { key: 'signal_nlrb', label: 'NLRB Activity' },
    ],
  },
  {
    category: 'leverage',
    label: 'Leverage Signals',
    icon: HandCoins,
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-200',
    signals: [
      { key: 'signal_contracts', label: 'Federal Contracts' },
      { key: 'signal_financial', label: 'Financial Profile' },
      { key: 'signal_union_density', label: 'Union Density' },
    ],
  },
  {
    category: 'context',
    label: 'Context Signals',
    icon: TrendingUp,
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
    signals: [
      { key: 'signal_industry_growth', label: 'Industry Growth' },
      { key: 'signal_size', label: 'Employer Size' },
    ],
  },
]

function strengthLabel(val) {
  if (val == null) return null
  if (val >= 7) return 'HIGH'
  if (val >= 4) return 'MEDIUM'
  return 'LOW'
}

function strengthColor(val) {
  if (val == null) return ''
  if (val >= 7) return 'text-red-700 bg-red-100'
  if (val >= 4) return 'text-amber-700 bg-amber-100'
  return 'text-stone-600 bg-stone-100'
}

function SignalRow({ label, value, explanation }) {
  const present = value != null
  const strength = strengthLabel(value)

  return (
    <div className="flex items-center justify-between py-1.5 px-2 hover:bg-muted/50">
      <div className="flex items-center gap-2 min-w-0">
        <span className={cn(
          'h-2 w-2 shrink-0 rounded-full',
          present ? 'bg-green-500' : 'bg-stone-300'
        )} />
        <span className="text-sm truncate">{label}</span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {present ? (
          <>
            <span className="text-xs tabular-nums font-medium">
              {Number(value).toFixed(1)}
            </span>
            <span className={cn(
              'inline-flex items-center px-1.5 py-0.5 text-[10px] font-semibold',
              strengthColor(value)
            )}>
              {strength}
            </span>
          </>
        ) : (
          <span className="text-xs text-muted-foreground">--</span>
        )}
      </div>
    </div>
  )
}

function SignalGroup({ group, scorecard, signalExplanations }) {
  const Icon = group.icon
  const presentCount = group.signals.filter(s => scorecard?.[s.key] != null).length
  const totalCount = group.signals.length

  return (
    <div className={cn('border rounded-md overflow-hidden', group.borderColor)}>
      <div className={cn('flex items-center gap-2 px-3 py-2', group.bgColor)}>
        <Icon className={cn('h-4 w-4', group.color)} />
        <span className={cn('text-sm font-semibold', group.color)}>{group.label}</span>
        <span className="ml-auto text-xs text-muted-foreground">{presentCount}/{totalCount}</span>
      </div>
      <div className="divide-y">
        {group.signals.map(({ key, label }) => (
          <SignalRow
            key={key}
            label={label}
            value={scorecard?.[key]}
            explanation={signalExplanations?.[key]}
          />
        ))}
      </div>
    </div>
  )
}

export function SignalInventory({ scorecard, signals }) {
  if (!scorecard) return null

  const signalsPresent = scorecard.signals_present ?? 0
  const totalSignals = 8
  const hasEnforcement = scorecard.has_enforcement ?? false
  const enforcementCount = scorecard.enforcement_count ?? 0

  // Build explanation map from signals array if provided
  const signalExplanations = {}
  if (signals) {
    for (const s of signals) {
      const key = `signal_${s.signal?.toLowerCase()?.replace(/[^a-z_]/g, '_')}` || s.key
      signalExplanations[key] = s.explanation
    }
  }

  // Header color based on enforcement
  const headerColor = hasEnforcement
    ? 'text-red-700'
    : signalsPresent > 0
      ? 'text-amber-700'
      : 'text-stone-500'

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Signal Inventory</CardTitle>
          <div className="flex items-center gap-2">
            <span className={cn('text-sm font-semibold', headerColor)}>
              {signalsPresent} of {totalSignals} signals detected
            </span>
            {hasEnforcement && (
              <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-semibold bg-red-600 text-white">
                {enforcementCount} ENFORCEMENT
              </span>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {SIGNAL_GROUPS.map((group) => (
            <SignalGroup
              key={group.category}
              group={group}
              scorecard={scorecard}
              signalExplanations={signalExplanations}
            />
          ))}
        </div>

        {/* Pillar summary */}
        {(scorecard.pillar_anger != null || scorecard.pillar_leverage != null) && (
          <div className="mt-4 pt-4 border-t">
            <div className="flex gap-4 text-sm">
              {scorecard.pillar_anger != null && (
                <div className="flex items-center gap-1.5">
                  <ShieldAlert className="h-3.5 w-3.5 text-red-500" />
                  <span className="text-muted-foreground">Anger:</span>
                  <span className="font-semibold">{Number(scorecard.pillar_anger).toFixed(1)}</span>
                </div>
              )}
              {scorecard.pillar_leverage != null && (
                <div className="flex items-center gap-1.5">
                  <HandCoins className="h-3.5 w-3.5 text-amber-500" />
                  <span className="text-muted-foreground">Leverage:</span>
                  <span className="font-semibold">{Number(scorecard.pillar_leverage).toFixed(1)}</span>
                </div>
              )}
              {scorecard.pillar_stability != null && (
                <div className="flex items-center gap-1.5">
                  <Users className="h-3.5 w-3.5 text-blue-500" />
                  <span className="text-muted-foreground">Stability:</span>
                  <span className="font-semibold">{Number(scorecard.pillar_stability).toFixed(1)}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
      <CardFooter>
        <p className="text-xs text-muted-foreground">
          Signals indicate data presence and strength, not a composite score. Use filters to discover targets.
          {scorecard.has_recent_violations && (
            <span className="ml-1 text-red-600 font-medium">Recent violations detected (within 2 years).</span>
          )}
        </p>
      </CardFooter>
    </Card>
  )
}
