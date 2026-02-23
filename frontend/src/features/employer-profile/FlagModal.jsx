import { useState } from 'react'
import { X } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { apiClient } from '@/shared/api/client'

const FLAG_TYPES = [
  { value: 'ALREADY_UNION', label: 'Already Unionized' },
  { value: 'DUPLICATE', label: 'Duplicate Entry' },
  { value: 'LABOR_ORG_NOT_EMPLOYER', label: 'Labor Org, Not Employer' },
  { value: 'DEFUNCT', label: 'Defunct / Closed' },
  { value: 'DATA_QUALITY', label: 'Data Quality Issue' },
  { value: 'NEEDS_REVIEW', label: 'Needs Review' },
]

export function FlagModal({ sourceType, sourceId, initialFlagType, onClose }) {
  const [flagType, setFlagType] = useState(initialFlagType || '')
  const [notes, setNotes] = useState('')
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: (data) => apiClient.post('/api/employers/flags', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['employer-flags'] })
      onClose()
    },
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!flagType) return
    mutation.mutate({
      source_type: sourceType,
      source_id: sourceId,
      flag_type: flagType,
      notes: notes.trim() || null,
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <Card className="w-full max-w-md mx-4">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Flag Employer</CardTitle>
            <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
              <X className="h-5 w-5" />
            </button>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-1 block">Flag Type</label>
              <Select
                value={flagType}
                onChange={(e) => setFlagType(e.target.value)}
                aria-label="Flag type"
              >
                <option value="">Select a type...</option>
                {FLAG_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Notes (optional)</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full min-h-[80px] px-3 py-2 text-sm border bg-background"
                placeholder="Add any additional context..."
              />
            </div>
            {mutation.isError && (
              <p className="text-sm text-destructive">
                {mutation.error?.message || 'Failed to submit flag'}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={!flagType || mutation.isPending}>
                {mutation.isPending ? 'Submitting...' : 'Submit Flag'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
