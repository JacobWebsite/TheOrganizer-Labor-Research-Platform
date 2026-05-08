import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { UnionWebProfileSection } from '@/features/union-explorer/UnionWebProfileSection'

const FULL_PROFILE = {
  id: 1510,
  parent_union: 'IBEW',
  local_number: '3',
  state: 'NY',
  website_url: 'http://www.local3.com',
  phone: '(718) 591-4000',
  fax: '(718) 380-8998',
  email: 'mail@local3ibew.org',
  address: '158-11 Harry Van Arsdale Jr. Avenue, Flushing, NY, 11365',
  officers: 'Christopher Erikson, Jr. (B.M.)\nThomas J. Cleary (Pres.)\nJoseph P. Proscia',
  scrape_status: 'DIRECTORY_ONLY',
  match_status: 'MATCHED_OLMS',
  source_directory_url: 'https://ibew.org/local-union-directory/',
  extra_data: {},
}

describe('UnionWebProfileSection', () => {
  it('renders nothing when webProfile is null', () => {
    const { container } = render(<UnionWebProfileSection webProfile={null} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders full profile with website, phone, fax, email, address, officers', () => {
    render(<UnionWebProfileSection webProfile={FULL_PROFILE} />)
    // Website button shows the hostname
    expect(screen.getByText('local3.com')).toBeInTheDocument()
    // Contact info
    expect(screen.getByText('(718) 591-4000')).toBeInTheDocument()
    expect(screen.getByText('(718) 380-8998')).toBeInTheDocument()
    expect(screen.getByText('mail@local3ibew.org')).toBeInTheDocument()
    // Address
    expect(screen.getByText(/Flushing, NY, 11365/)).toBeInTheDocument()
    // Officers
    expect(screen.getByText('Officers (3)')).toBeInTheDocument()
    expect(screen.getByText(/Christopher Erikson, Jr\./)).toBeInTheDocument()
    expect(screen.getByText(/B\.M\./)).toBeInTheDocument()
    // One officer without position still renders by name
    expect(screen.getByText('Joseph P. Proscia')).toBeInTheDocument()
  })

  it('shows sourced-from label with parent union name', () => {
    render(<UnionWebProfileSection webProfile={FULL_PROFILE} />)
    expect(screen.getByText(/Sourced from IBEW directory/)).toBeInTheDocument()
  })

  it('renders email-only profile without crashing', () => {
    const emailOnly = {
      parent_union: 'APWU',
      email: 'local99@apwu.org',
      source_directory_url: 'https://apwu.org/apwu-local-and-state-organization-links/',
    }
    render(<UnionWebProfileSection webProfile={emailOnly} />)
    expect(screen.getByText('local99@apwu.org')).toBeInTheDocument()
    // No phone/fax/officers shown
    expect(screen.queryByText(/Officers/)).not.toBeInTheDocument()
  })

  it('shows empty state when only parent_union is populated', () => {
    const bare = { parent_union: 'CWA' }
    render(<UnionWebProfileSection webProfile={bare} />)
    expect(
      screen.getByText(/No contact information recorded/)
    ).toBeInTheDocument()
  })

  it('website URL hostname strips www. prefix', () => {
    const withWww = { ...FULL_PROFILE, website_url: 'https://www.cwa-union.org/locals/1234' }
    render(<UnionWebProfileSection webProfile={withWww} />)
    expect(screen.getByText('cwa-union.org')).toBeInTheDocument()
  })

  it('handles malformed URL without crashing', () => {
    const bad = { ...FULL_PROFILE, website_url: 'not-a-url-at-all' }
    const { container } = render(<UnionWebProfileSection webProfile={bad} />)
    // Should still render contact info
    expect(container.innerHTML).toContain('718')
  })
})
