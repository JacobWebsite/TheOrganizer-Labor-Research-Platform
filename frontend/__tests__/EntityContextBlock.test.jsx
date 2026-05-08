import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EntityContextBlock } from '@/features/employer-profile/EntityContextBlock'

describe('EntityContextBlock', () => {
  it('falls back to legacy workers chip when entityContext is missing', () => {
    render(<EntityContextBlock entityContext={null} legacyWorkers={119} />)
    expect(screen.getByText(/119/)).toBeInTheDocument()
    expect(screen.getByText(/workers/)).toBeInTheDocument()
  })

  it('renders unit_primary with group as secondary for Starbucks-shape data', () => {
    const ec = {
      display_mode: 'unit_primary',
      unit: { count: 90, city: 'Anaheim', state: 'CA', label: 'This unit' },
      group: { count: 119, member_count: 234, canonical_name: 'Starbucks', label: 'Group' },
      family: null,
    }
    render(<EntityContextBlock entityContext={ec} />)
    // Primary row: unit count
    expect(screen.getByText('90')).toBeInTheDocument()
    expect(screen.getByText('This unit')).toBeInTheDocument()
    // Secondary: group workers count + member_count annotation
    expect(screen.getByText('119')).toBeInTheDocument()
    expect(screen.getByText('Group')).toBeInTheDocument()
    expect(screen.getByText(/234 units/)).toBeInTheDocument()
  })

  it('renders family_primary with corp-family label and group + unit stacked', () => {
    const ec = {
      display_mode: 'family_primary',
      unit: { count: 50, city: 'Cambridge', state: 'MA', label: 'This unit' },
      group: { count: 9142, member_count: 87, canonical_name: 'Starbucks', label: 'Group' },
      family: {
        primary_count: 381000,
        primary_source: 'sec_10k',
        sec_count: 381000,
        mergent_count: 402000,
        ultimate_parent_name: 'STARBUCKS CORP',
        is_ultimate_parent_rollup: true,
        range: { low: 381000, high: 402000, display: '381K\u2013402K' },
        conflict: { present: false, spread_pct: null, sources_disagreeing: [] },
        label: 'Corp. Family',
      },
    }
    render(<EntityContextBlock entityContext={ec} />)
    // Primary displays the range string, NOT the single number
    expect(screen.getByText('381K\u2013402K')).toBeInTheDocument()
    expect(screen.getByText('Corp. Family')).toBeInTheDocument()
    // Secondary rows for group and unit
    expect(screen.getByText('9,142')).toBeInTheDocument()
    expect(screen.getByText('Group')).toBeInTheDocument()
    expect(screen.getByText('50')).toBeInTheDocument()
    expect(screen.getByText(/Cambridge, MA/)).toBeInTheDocument()
  })

  it('renders conflict badge when sources disagree by more than 25%', () => {
    const ec = {
      display_mode: 'family_primary',
      unit: null,
      group: null,
      family: {
        primary_count: 200000,
        primary_source: 'sec_10k',
        sec_count: 200000,
        mergent_count: 500000,
        ultimate_parent_name: null,
        is_ultimate_parent_rollup: false,
        range: null,
        conflict: {
          present: true,
          spread_pct: 60.0,
          sources_disagreeing: ['sec_10k', 'mergent_company'],
        },
        label: 'Corp. Family',
      },
    }
    render(<EntityContextBlock entityContext={ec} />)
    // Primary: SEC number (not a range)
    expect(screen.getByText('200,000')).toBeInTheDocument()
    // Conflict badge
    expect(screen.getByText(/sources disagree/i)).toBeInTheDocument()
  })
})
