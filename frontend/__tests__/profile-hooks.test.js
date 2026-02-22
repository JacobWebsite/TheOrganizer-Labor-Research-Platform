import { describe, it, expect } from 'vitest'
import { parseCanonicalId } from '@/shared/api/profile'

describe('parseCanonicalId', () => {
  it('identifies plain hex as F7', () => {
    const result = parseCanonicalId('e1880d4530539a4a')
    expect(result).toEqual({ isF7: true, sourceType: 'F7', rawId: 'e1880d4530539a4a' })
  })

  it('identifies NLRB-prefixed IDs', () => {
    const result = parseCanonicalId('NLRB-12345')
    expect(result).toEqual({ isF7: false, sourceType: 'NLRB', rawId: '12345' })
  })

  it('identifies VR-prefixed IDs', () => {
    const result = parseCanonicalId('VR-456')
    expect(result).toEqual({ isF7: false, sourceType: 'VR', rawId: '456' })
  })

  it('identifies MANUAL-prefixed IDs', () => {
    const result = parseCanonicalId('MANUAL-789')
    expect(result).toEqual({ isF7: false, sourceType: 'MANUAL', rawId: '789' })
  })

  it('handles null/undefined input', () => {
    expect(parseCanonicalId(null)).toEqual({ isF7: false, sourceType: 'UNKNOWN', rawId: null })
    expect(parseCanonicalId(undefined)).toEqual({ isF7: false, sourceType: 'UNKNOWN', rawId: undefined })
  })

  it('treats unknown prefixes as F7 (hex)', () => {
    const result = parseCanonicalId('abc123def')
    expect(result).toEqual({ isF7: true, sourceType: 'F7', rawId: 'abc123def' })
  })

  it('handles NLRB IDs with dashes in the raw portion', () => {
    const result = parseCanonicalId('NLRB-01-CA-123456')
    expect(result).toEqual({ isF7: false, sourceType: 'NLRB', rawId: '01-CA-123456' })
  })
})
