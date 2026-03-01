import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FactRow } from '@/features/research/FactRow'

function renderRow(fact, onReview) {
  return render(
    <table>
      <tbody>
        <FactRow fact={fact} onReview={onReview} />
      </tbody>
    </table>
  )
}

const BASE_FACT = {
  fact_id: 42,
  attribute_name: 'employee_count',
  display_name: 'Employee Count',
  attribute_value: '500',
  attribute_value_json: null,
  source_name: 'database',
  confidence: 0.9,
  as_of_date: '2025-01-01',
  human_verdict: null,
  contradicts_fact_id: null,
}

describe('FactRow', () => {
  it('renders review buttons when no verdict exists', () => {
    const onReview = vi.fn()
    renderRow(BASE_FACT, onReview)

    expect(screen.getByTitle('Confirm fact')).toBeTruthy()
    expect(screen.getByTitle('Reject fact')).toBeTruthy()
    expect(screen.getByTitle('Mark irrelevant')).toBeTruthy()
  })

  it('renders verdict badge when verdict exists', () => {
    const fact = { ...BASE_FACT, human_verdict: 'confirmed' }
    renderRow(fact)

    expect(screen.getByText('Confirmed')).toBeTruthy()
    // Should NOT show review buttons
    expect(screen.queryByTitle('Confirm fact')).toBeNull()
  })

  it('calls onReview with correct args on button click', () => {
    const onReview = vi.fn()
    renderRow(BASE_FACT, onReview)

    fireEvent.click(screen.getByTitle('Reject fact'))

    expect(onReview).toHaveBeenCalledTimes(1)
    expect(onReview).toHaveBeenCalledWith(42, 'rejected')
  })

  it('shows warning icon when fact has contradiction', () => {
    const fact = { ...BASE_FACT, contradicts_fact_id: 10 }
    renderRow(fact, vi.fn())

    // The AlertTriangle icon should be present (title attribute)
    expect(screen.getByTitle('Contradicts another fact')).toBeTruthy()
  })
})
