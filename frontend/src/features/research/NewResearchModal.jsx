import { useState } from 'react'
import { X } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { useStates } from '@/shared/api/lookups'

const COMPANY_TYPES = [
  { value: '', label: 'Any type' },
  { value: 'public', label: 'Public' },
  { value: 'private', label: 'Private' },
  { value: 'nonprofit', label: 'Nonprofit' },
  { value: 'government', label: 'Government' },
]

export function NewResearchModal({ onSubmit, isPending, error, onClose }) {
  const [companyName, setCompanyName] = useState('')
  const [naicsCode, setNaicsCode] = useState('')
  const [state, setState] = useState('')
  const [companyType, setCompanyType] = useState('')
  const statesQuery = useStates()
  const states = statesQuery.data?.states || []

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!companyName.trim()) return
    onSubmit({
      company_name: companyName.trim(),
      naics_code: naicsCode || undefined,
      state: state || undefined,
      company_type: companyType || undefined,
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <Card className="w-full max-w-md mx-4">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>New Research Deep Dive</CardTitle>
            <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
              <X className="h-5 w-5" />
            </button>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-1 block">Company Name *</label>
              <input
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="e.g. Amazon, Starbucks, Kaiser Permanente"
                className="h-10 w-full border border-input bg-background px-3 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                autoFocus
              />
            </div>

            <div>
              <label className="text-sm font-medium mb-1 block">NAICS Code (optional)</label>
              <input
                type="text"
                value={naicsCode}
                onChange={(e) => setNaicsCode(e.target.value)}
                placeholder="e.g. 722511"
                className="h-10 w-full border border-input bg-background px-3 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>

            <div>
              <label className="text-sm font-medium mb-1 block">State (optional)</label>
              <Select
                value={state}
                onChange={(e) => setState(e.target.value)}
                aria-label="State"
              >
                <option value="">Any state</option>
                {states.map((s) => (
                  <option key={s.state} value={s.state}>{s.state}</option>
                ))}
              </Select>
            </div>

            <div>
              <label className="text-sm font-medium mb-1 block">Company Type (optional)</label>
              <Select
                value={companyType}
                onChange={(e) => setCompanyType(e.target.value)}
                aria-label="Company type"
              >
                {COMPANY_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </Select>
            </div>

            {error && (
              <p className="text-sm text-destructive">
                {error.message || 'Failed to start research'}
              </p>
            )}

            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={!companyName.trim() || isPending}>
                {isPending ? 'Starting...' : 'Start Research'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
