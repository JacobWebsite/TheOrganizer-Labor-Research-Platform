import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FeedbackModal } from '@/shared/components/FeedbackModal'

vi.mock('@/shared/api/feedback', () => ({
  submitFeedback: vi.fn(() =>
    Promise.resolve({ id: 1, created_at: '2026-07-11T00:00:00Z', status: 'received' })
  ),
}))

import { submitFeedback } from '@/shared/api/feedback'

function renderModal(props = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const onClose = vi.fn()
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackModal onClose={onClose} {...props} />
    </QueryClientProvider>
  )
  return { onClose }
}

describe('FeedbackModal', () => {
  beforeEach(() => {
    submitFeedback.mockClear()
    submitFeedback.mockResolvedValue({
      id: 1,
      created_at: '2026-07-11T00:00:00Z',
      status: 'received',
    })
  })

  it('renders the feedback form', () => {
    renderModal()
    expect(screen.getByLabelText('Feedback category')).toBeInTheDocument()
    expect(screen.getByLabelText('Tell us more')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send feedback' })).toBeInTheDocument()
  })

  it('keeps submit disabled until a category and message are entered', () => {
    renderModal()
    const submit = screen.getByRole('button', { name: 'Send feedback' })
    expect(submit).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Feedback category'), {
      target: { value: 'bug' },
    })
    fireEvent.change(screen.getByLabelText('Tell us more'), {
      target: { value: 'Button does nothing.' },
    })
    expect(submit).not.toBeDisabled()
  })

  it('submits feedback with the chosen category and message, then confirms', async () => {
    renderModal({ employerId: 'M123' })
    fireEvent.change(screen.getByLabelText('Feedback category'), {
      target: { value: 'data_issue' },
    })
    fireEvent.change(screen.getByLabelText('Tell us more'), {
      target: { value: 'OSHA count looks off.' },
    })
    // Submit the form directly: jsdom does not synthesize form submission from a
    // submit-button click the way a real browser does.
    fireEvent.submit(
      screen.getByRole('button', { name: 'Send feedback' }).closest('form')
    )

    // react-query invokes the mutation fn asynchronously, so wait for the call.
    await waitFor(() =>
      expect(submitFeedback).toHaveBeenCalledWith(
        expect.objectContaining({
          category: 'data_issue',
          message: 'OSHA count looks off.',
          employer_id: 'M123',
        })
      )
    )
    await waitFor(() =>
      expect(screen.getByText('Thank you!')).toBeInTheDocument()
    )
  })

  it('closes when Cancel is clicked', () => {
    const { onClose } = renderModal()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalled()
  })
})
