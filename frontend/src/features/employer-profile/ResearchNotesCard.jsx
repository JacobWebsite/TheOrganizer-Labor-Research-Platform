import { useState } from 'react'
import { StickyNote } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { useEmployerFlags, useFlagEmployer } from '@/shared/api/profile'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'

const FLAG_TYPES = [
  { value: 'ALREADY_UNION', label: 'Already Unionized', color: 'bg-green-50 text-green-700' },
  { value: 'DUPLICATE', label: 'Duplicate', color: 'bg-amber-50 text-amber-700' },
  { value: 'LABOR_ORG_NOT_EMPLOYER', label: 'Labor Org', color: 'bg-purple-50 text-purple-700' },
  { value: 'DEFUNCT', label: 'Defunct', color: 'bg-stone-100 text-stone-600' },
  { value: 'DATA_QUALITY', label: 'Data Quality', color: 'bg-red-50 text-red-700' },
  { value: 'NEEDS_REVIEW', label: 'Needs Review', color: 'bg-blue-50 text-blue-700' },
  { value: 'VERIFIED_OK', label: 'Verified OK', color: 'bg-green-100 text-green-800' },
  { value: 'HOT_TARGET', label: 'Hot Target', color: 'bg-orange-50 text-orange-700' },
  { value: 'NEEDS_RESEARCH', label: 'Needs Research', color: 'bg-cyan-50 text-cyan-700' },
  { value: 'ACTIVE_CAMPAIGN', label: 'Active Campaign', color: 'bg-rose-50 text-rose-700' },
  { value: 'FOLLOW_UP', label: 'Follow Up', color: 'bg-yellow-50 text-yellow-700' },
  { value: 'DEAD_END', label: 'Dead End', color: 'bg-gray-100 text-gray-600' },
]

const PRIORITY_OPTIONS = [
  { value: '', label: 'No priority' },
  { value: 'HIGH', label: 'High' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'LOW', label: 'Low' },
]

const PRIORITY_STYLES = {
  HIGH: 'bg-red-100 text-red-700',
  MEDIUM: 'bg-yellow-100 text-yellow-700',
  LOW: 'bg-slate-100 text-slate-600',
}

function getFlagStyle(type) {
  return FLAG_TYPES.find((f) => f.value === type)?.color || 'bg-stone-100 text-stone-600'
}

function getFlagLabel(type) {
  return FLAG_TYPES.find((f) => f.value === type)?.label || type
}

export function ResearchNotesCard({ employerId, sourceType, sourceId }) {
  const { data, isLoading } = useEmployerFlags(employerId)
  const flagMutation = useFlagEmployer()
  const [showForm, setShowForm] = useState(false)
  const [flagType, setFlagType] = useState('')
  const [priority, setPriority] = useState('')
  const [notes, setNotes] = useState('')

  const flags = data?.flags || []
  const summary = flags.length > 0 ? `${flags.length} notes` : 'No research notes'

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!flagType) return
    flagMutation.mutate({
      source_type: sourceType || 'F7',
      source_id: sourceId || employerId,
      flag_type: flagType,
      priority: priority || null,
      notes: notes.trim() || null,
    }, {
      onSuccess: () => {
        setFlagType('')
        setPriority('')
        setNotes('')
        setShowForm(false)
      },
    })
  }

  return (
    <CollapsibleCard icon={StickyNote} title="Research Notes" summary={summary}>
      <div className="space-y-3">
        {flags.length > 0 && (
          <div className="space-y-2">
            {flags.map((f) => (
              <div key={f.id} className="flex items-start gap-2 text-sm border-b pb-2">
                <span className={`inline-flex px-1.5 py-0.5 text-[10px] font-medium shrink-0 ${getFlagStyle(f.flag_type)}`}>
                  {getFlagLabel(f.flag_type)}
                </span>
                {f.priority && (
                  <span className={`inline-flex px-1.5 py-0.5 text-[10px] font-medium shrink-0 ${PRIORITY_STYLES[f.priority] || ''}`}>
                    {f.priority}
                  </span>
                )}
                <div className="flex-1 min-w-0">
                  {f.notes && <p className="text-sm">{f.notes}</p>}
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {new Date(f.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}

        {!showForm ? (
          <Button variant="outline" size="sm" onClick={() => setShowForm(true)}>
            Add Note
          </Button>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3 border-t pt-3">
            <div>
              <label className="text-xs font-medium mb-1 block">Type</label>
              <Select value={flagType} onChange={(e) => setFlagType(e.target.value)} aria-label="Note type">
                <option value="">Select type...</option>
                {FLAG_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </Select>
            </div>
            <div>
              <label className="text-xs font-medium mb-1 block">Priority</label>
              <Select value={priority} onChange={(e) => setPriority(e.target.value)} aria-label="Priority">
                {PRIORITY_OPTIONS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </Select>
            </div>
            <div>
              <label className="text-xs font-medium mb-1 block">Notes</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full min-h-[60px] px-3 py-2 text-sm border bg-background"
                placeholder="Add context..."
              />
            </div>
            {flagMutation.isError && (
              <p className="text-xs text-destructive">{flagMutation.error?.message || 'Failed to save'}</p>
            )}
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={!flagType || flagMutation.isPending}>
                {flagMutation.isPending ? 'Saving...' : 'Save'}
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
