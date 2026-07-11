import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { WelcomePage } from '@/features/onboarding/WelcomePage'

function renderWelcome() {
  return render(
    <MemoryRouter>
      <WelcomePage />
    </MemoryRouter>
  )
}

describe('WelcomePage', () => {
  it('renders the welcome heading and dossier walkthrough', () => {
    renderWelcome()
    expect(
      screen.getByRole('heading', { name: /Welcome to The Organizer/i })
    ).toBeInTheDocument()
    expect(screen.getByText(/How to read a dossier/i)).toBeInTheDocument()
    expect(screen.getByText(/Score and tier/i)).toBeInTheDocument()
  })

  it('links to search and targets so testers can open a real dossier', () => {
    renderWelcome()
    expect(
      screen.getByRole('link', { name: /Search for an employer/i })
    ).toHaveAttribute('href', '/search')
    expect(
      screen.getByRole('link', { name: /Browse organizing targets/i })
    ).toHaveAttribute('href', '/targets')
  })

  it('points testers to the feedback button', () => {
    renderWelcome()
    expect(screen.getByText(/Tell us what breaks/i)).toBeInTheDocument()
  })
})
