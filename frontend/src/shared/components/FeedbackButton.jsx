import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { MessageSquare } from 'lucide-react'
import { FeedbackModal } from './FeedbackModal'

/**
 * Persistent floating "Feedback" button (beta onboarding, roadmap W8).
 * Rendered once in Layout so it is available on every page.
 * On employer profile pages, tags the submission with the employer id
 * so dossier feedback is triageable.
 */
export function FeedbackButton() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const employerId = pathname.match(/^\/employers\/([^/]+)/)?.[1] ?? null
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        data-no-print
        aria-label="Send feedback"
        className="fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium shadow-lg transition-transform hover:scale-105"
        style={{ backgroundColor: '#c78c4e', color: '#2c2418' }}
      >
        <MessageSquare className="h-4 w-4" />
        Feedback
      </button>
      {open && <FeedbackModal onClose={() => setOpen(false)} employerId={employerId} />}
    </>
  )
}
