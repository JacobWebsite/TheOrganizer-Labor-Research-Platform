import { useState } from 'react'
import { X } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { submitFeedback } from '@/shared/api/feedback'

const CATEGORIES = [
  { value: 'bug', label: 'Something is broken' },
  { value: 'confusing', label: 'This is confusing' },
  { value: 'data_issue', label: 'The data looks wrong' },
  { value: 'feature_request', label: 'I wish it could...' },
  { value: 'praise', label: 'This is great' },
  { value: 'other', label: 'Something else' },
]

export function FeedbackModal({ onClose, employerId }) {
  const [category, setCategory] = useState('')
  const [message, setMessage] = useState('')
  const [done, setDone] = useState(false)

  const mutation = useMutation({
    mutationFn: (data) => submitFeedback(data),
    onSuccess: () => setDone(true),
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!category || !message.trim()) return
    mutation.mutate({
      category,
      message: message.trim(),
      employer_id: employerId || null,
      page_url:
        typeof window !== 'undefined'
          ? window.location.pathname + window.location.search
          : null,
      user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
    })
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-label="Send feedback"
    >
      <Card className="w-full max-w-md mx-4">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>{done ? 'Thank you!' : 'Send feedback'}</CardTitle>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </CardHeader>
        <CardContent>
          {done ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Your feedback was recorded. Thank you for helping improve The Organizer.
              </p>
              <div className="flex justify-end">
                <Button size="sm" onClick={onClose}>
                  Close
                </Button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label
                  className="text-sm font-medium mb-1 block"
                  htmlFor="feedback-category"
                >
                  What kind of feedback?
                </label>
                <Select
                  id="feedback-category"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  aria-label="Feedback category"
                >
                  <option value="">Select...</option>
                  {CATEGORIES.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <label
                  className="text-sm font-medium mb-1 block"
                  htmlFor="feedback-message"
                >
                  Tell us more
                </label>
                <textarea
                  id="feedback-message"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  className="w-full min-h-[100px] px-3 py-2 text-sm border bg-background"
                  placeholder="What happened, or what would make this better?"
                />
              </div>
              {mutation.isError && (
                <p className="text-sm text-destructive">
                  {mutation.error?.message || 'Failed to send feedback'}
                </p>
              )}
              <div className="flex justify-end gap-2">
                <Button type="button" variant="outline" size="sm" onClick={onClose}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={!category || !message.trim() || mutation.isPending}
                >
                  {mutation.isPending ? 'Sending...' : 'Send feedback'}
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
