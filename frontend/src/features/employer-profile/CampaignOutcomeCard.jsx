import { useState } from 'react'
import { Flag } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { useCampaignOutcomes, useRecordOutcome } from '@/shared/api/campaigns'

const OUTCOME_OPTIONS = [
  { value: 'won', label: 'Won' },
  { value: 'lost', label: 'Lost' },
  { value: 'abandoned', label: 'Abandoned' },
  { value: 'in_progress', label: 'In Progress' },
]

const OUTCOME_STYLES = {
  won: 'bg-[#3a7d44]/15 text-[#3a7d44] border-[#3a7d44]/30',
  lost: 'bg-[#c23a22]/15 text-[#c23a22] border-[#c23a22]/30',
  abandoned: 'bg-[#8a7e6b]/15 text-[#8a7e6b] border-[#8a7e6b]/30',
  in_progress: 'bg-[#3a6b8c]/15 text-[#3a6b8c] border-[#3a6b8c]/30',
}

function labelForOutcome(outcome) {
  return OUTCOME_OPTIONS.find((option) => option.value === outcome)?.label || outcome
}

export function CampaignOutcomeCard({ employerId, employerName }) {
  const { data, isLoading } = useCampaignOutcomes(employerId)
  const recordOutcome = useRecordOutcome()
  const [showForm, setShowForm] = useState(false)
  const [outcome, setOutcome] = useState('in_progress')
  const [notes, setNotes] = useState('')
  const [reportedBy, setReportedBy] = useState('')
  const [outcomeDate, setOutcomeDate] = useState('')

  const outcomes = data?.outcomes || []
  const summary = outcomes.length > 0 ? `${outcomes.length} recorded` : 'No recorded outcomes'

  function handleSubmit(event) {
    event.preventDefault()
    if (!outcome) return
    recordOutcome.mutate({
      employer_id: employerId,
      employer_name: employerName,
      outcome,
      notes: notes.trim() || null,
      reported_by: reportedBy.trim() || null,
      outcome_date: outcomeDate || null,
    }, {
      onSuccess: () => {
        setNotes('')
        setReportedBy('')
        setOutcomeDate('')
        setOutcome('in_progress')
        setShowForm(false)
      },
    })
  }

  return (
    <CollapsibleCard icon={Flag} title="Campaign Outcomes" summary={summary} defaultOpen={false}>
      <div className="space-y-3">
        {isLoading && <p className="text-sm text-muted-foreground">Loading outcomes...</p>}
        {!isLoading && outcomes.length === 0 && (
          <p className="text-sm text-muted-foreground">No outcomes recorded yet for this employer.</p>
        )}
        {outcomes.length > 0 && (
          <div className="space-y-2">
            {outcomes.map((item) => (
              <div key={item.id} className="rounded-md border bg-card px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold ${OUTCOME_STYLES[item.outcome] || ''}`}>
                    {labelForOutcome(item.outcome)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {item.outcome_date ? new Date(item.outcome_date).toLocaleDateString() : 'Date not recorded'}
                  </span>
                  {item.reported_by && (
                    <span className="text-xs text-muted-foreground">Reported by {item.reported_by}</span>
                  )}
                </div>
                {item.notes && <p className="mt-2 text-sm">{item.notes}</p>}
              </div>
            ))}
          </div>
        )}

        {!showForm ? (
          <Button variant="outline" size="sm" onClick={() => setShowForm(true)}>
            Record Outcome
          </Button>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3 border-t pt-3">
            <div>
              <label htmlFor="campaign-outcome" className="mb-1 block text-xs font-medium">Outcome</label>
              <Select id="campaign-outcome" value={outcome} onChange={(e) => setOutcome(e.target.value)} aria-label="Outcome">
                {OUTCOME_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </Select>
            </div>
            <div>
              <label htmlFor="campaign-reported-by" className="mb-1 block text-xs font-medium">Reported By</label>
              <input
                id="campaign-reported-by"
                value={reportedBy}
                onChange={(e) => setReportedBy(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                placeholder="Organizer or source"
              />
            </div>
            <div>
              <label htmlFor="campaign-outcome-date" className="mb-1 block text-xs font-medium">Outcome Date</label>
              <input
                id="campaign-outcome-date"
                type="date"
                value={outcomeDate}
                onChange={(e) => setOutcomeDate(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label htmlFor="campaign-outcome-notes" className="mb-1 block text-xs font-medium">Notes</label>
              <textarea
                id="campaign-outcome-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="min-h-[80px] w-full rounded-md border bg-background px-3 py-2 text-sm"
                placeholder="What happened, what changed, and any context worth preserving."
              />
            </div>
            {recordOutcome.isError && (
              <p className="text-xs text-destructive">{recordOutcome.error?.message || 'Failed to save outcome.'}</p>
            )}
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={recordOutcome.isPending}>
                {recordOutcome.isPending ? 'Saving...' : 'Save Outcome'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setShowForm(false)}>
                Cancel
              </Button>
            </div>
          </form>
        )}
      </div>
    </CollapsibleCard>
  )
}
