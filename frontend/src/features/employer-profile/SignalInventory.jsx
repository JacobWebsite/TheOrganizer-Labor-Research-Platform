import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card'
import { ShieldAlert, HandCoins, TrendingUp, Users } from 'lucide-react'
import { cn } from '@/lib/utils'

const SIGNAL_GROUPS = [
  {
    category: 'enforcement',
    label: 'Enforcement Signals',
    icon: ShieldAlert,
    color: 'text-[#c23a22]',
    bgColor: 'bg-[#c23a22]/10',
    borderColor: 'border-[#c23a22]/20',
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
    color: 'text-[#c78c4e]',
    bgColor: 'bg-[#c78c4e]/10',
    borderColor: 'border-[#c78c4e]/20',
    signals: [
      { key: 'signal_contracts', label: 'Federal Contracts' },
      { key: 'signal_financial', label: 'Financial Profile' },
      { key: 'signal_union_density', label: 'Union Density' },
      { key: 'signal_similarity', label: 'Peer Similarity' },
    ],
  },
  {
    category: 'context',
    label: 'Context Signals',
    icon: TrendingUp,
    color: 'text-[#3a6b8c]',
    bgColor: 'bg-[#3a6b8c]/10',
    borderColor: 'border-[#3a6b8c]/20',
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
  if (val >= 7) return 'text-[#c23a22] bg-[#c23a22]/10'
  if (val >= 4) return 'text-[#c78c4e] bg-[#c78c4e]/15'
  return 'text-[#8a7e6b] bg-[#d9cebb]/50'
}

function SignalBar({ value }) {
  if (value == null) return null
  const pct = Math.min(Number(value) / 10 * 100, 100)
  return (
    <div className="w-full bg-[#E8DCC8] rounded h-1.5 mt-1">
      <div
        className={cn(
          'h-full rounded transition-all',
          value >= 7 ? 'bg-[#c23a22]' : value >= 4 ? 'bg-[#c78c4e]' : 'bg-[#8a7e6b]'
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function SignalRow({ label, value, explanation }) {
  const present = value != null
  const strength = strengthLabel(value)

  return (
    <div className="py-2 px-2 hover:bg-accent/50">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className={cn(
            'h-2 w-2 shrink-0 rounded-full',
            present ? 'bg-[#3a7d44]' : 'bg-[#d9cebb]'
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
                'inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold',
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
      {present && <SignalBar value={value} />}
      {explanation && (
        <p className="text-[11px] text-[#3D2B1F]/60 mt-1 ml-4 leading-tight">{explanation}</p>
      )}
    </div>
  )
}

function SignalGroup({ group, scorecard, signalExplanations }) {
  const Icon = group.icon
  const presentCount = group.signals.filter(s => scorecard?.[s.key] != null).length
  const totalCount = group.signals.length

  return (
    <div className={cn('border rounded-lg overflow-hidden', group.borderColor)}>
      <div className={cn('flex items-center gap-2 px-3 py-2', group.bgColor)}>
        <Icon className={cn('h-4 w-4', group.color)} />
        <span className={cn('text-sm font-semibold', group.color)}>{group.label}</span>
        <span className="ml-auto text-xs text-muted-foreground">{presentCount}/{totalCount}</span>
      </div>
      <div className="divide-y divide-border">
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
  // Count total signal keys across all groups
  const totalSignals = SIGNAL_GROUPS.reduce((n, g) => n + g.signals.length, 0)
  const hasEnforcement = scorecard.has_enforcement ?? false
  const enforcementCount = scorecard.enforcement_count ?? 0

  // Build explanation map from signals array if provided
  const signalExplanations = {}
  if (signals) {
    for (const s of signals) {
      // Map from API signal names to scorecard keys
      const nameMap = {
        'osha safety': 'signal_osha',
        'wage & hour': 'signal_whd',
        'nlrb activity': 'signal_nlrb',
        'federal contracts': 'signal_contracts',
        'financial profile': 'signal_financial',
        'union density': 'signal_union_density',
        'industry growth': 'signal_industry_growth',
        'employer size': 'signal_size',
        'peer similarity': 'signal_similarity',
        'wage context': 'wage_context',
      }
      const key = nameMap[s.signal?.toLowerCase()] || s.key
      if (key) signalExplanations[key] = s.explanation
    }
  }

  // Header color based on enforcement
  const headerColor = hasEnforcement
    ? 'text-[#c23a22]'
    : signalsPresent > 0
      ? 'text-[#c78c4e]'
      : 'text-[#8a7e6b]'

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
              <span className="inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-semibold bg-[#c23a22] text-white">
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
                  <ShieldAlert className="h-3.5 w-3.5 text-[#c23a22]" />
                  <span className="text-muted-foreground">Anger:</span>
                  <span className="font-semibold">{Number(scorecard.pillar_anger).toFixed(1)}</span>
                </div>
              )}
              {scorecard.pillar_leverage != null && (
                <div className="flex items-center gap-1.5">
                  <HandCoins className="h-3.5 w-3.5 text-[#c78c4e]" />
                  <span className="text-muted-foreground">Leverage:</span>
                  <span className="font-semibold">{Number(scorecard.pillar_leverage).toFixed(1)}</span>
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
            <span className="ml-1 text-[#c23a22] font-medium">Recent violations detected (within 2 years).</span>
          )}
        </p>
      </CardFooter>
    </Card>
  )
}
