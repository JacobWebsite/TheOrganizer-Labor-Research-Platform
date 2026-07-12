import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FeedbackButton } from '@/shared/components/FeedbackButton'

vi.mock('@/shared/api/feedback', () => ({
  submitFeedback: vi.fn(() =>
    Promise.resolve({ id: 1, created_at: '2026-07-12T00:00:00Z', status: 'received' })
  ),
}))

import { submitFeedback } from '@/shared/api/feedback'

function renderAt(path) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <FeedbackButton />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

function openFillSubmit() {
  fireEvent.click(screen.getByRole('button', { name: 'Send feedback' }))
  fireEvent.change(screen.getByLabelText('Feedback category'), {
    target: { value: 'bug' },
  })
  fireEvent.change(screen.getByLabelText('Tell us more'), {
    target: { value: 'Something broke.' },
  })
  fireEvent.submit(
    screen.getAllByRole('button', { name: 'Send feedback' }).at(-1).closest('form')
  )
}

describe('FeedbackButton', () => {
  beforeEach(() => {
    submitFeedback.mockClear()
  })

  it('tags submissions with the employer id on profile pages', async () => {
    renderAt('/employers/MASTER-155254')
    openFillSubmit()
    await waitFor(() =>
      expect(submitFeedback).toHaveBeenCalledWith(
        expect.objectContaining({ employer_id: 'MASTER-155254' })
      )
    )
  })

  it('sends null employer id on non-profile pages', async () => {
    renderAt('/targets')
    openFillSubmit()
    await waitFor(() =>
      expect(submitFeedback).toHaveBeenCalledWith(
        expect.objectContaining({ employer_id: null })
      )
    )
  })
})
