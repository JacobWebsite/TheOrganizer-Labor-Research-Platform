import { Link } from 'react-router-dom'
import { Search, Target, MessageSquare, ClipboardList } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { buttonVariants } from '@/components/ui/button'

/**
 * Beta tester welcome / onboarding page (roadmap W8).
 * Welcome + plain-English intro + a walkthrough of what's in an employer dossier.
 * Reachable at /welcome and from the "Getting Started" nav link.
 */

const DOSSIER_SECTIONS = [
  {
    title: 'Score and tier',
    body:
      'A single 0-100 signal-strength score, plus a tier (Priority, Strong, Promising, ...). It flags a workplace as worth investigating -- it does NOT predict whether a union drive would win.',
  },
  {
    title: 'Enforcement history',
    body:
      'Safety citations (OSHA), wage-and-hour violations (WHD), and labor-board activity (NLRB petitions and charges). Blank means "no records found," which is not the same as "no problems."',
  },
  {
    title: 'Corporate structure',
    body:
      'Who owns and controls the company -- parent companies, subsidiaries, board members, and major shareholders -- so you can see the real decision-makers behind a location.',
  },
  {
    title: 'Money and influence',
    body:
      'Financial filings, federal contracts, lobbying, and political contributions. This is how you understand a company’s resources and pressure points.',
  },
  {
    title: 'Union context',
    body:
      'Existing contracts, nearby organized workplaces, and comparable employers that already have a union -- the "what does an organized version of this look like" picture.',
  },
  {
    title: 'Where the data comes from',
    body:
      'Every card shows its sources and how fresh they are. When something looks off, that provenance is exactly what the Feedback button is for.',
  },
]

export function WelcomePage() {
  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <header className="space-y-3">
        <span
          className="inline-block rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide"
          style={{ backgroundColor: '#c78c4e', color: '#2c2418' }}
        >
          Private Beta
        </span>
        <h1 className="font-editorial text-3xl font-bold tracking-tight">
          Welcome to The Organizer
        </h1>
        <p className="text-muted-foreground">
          The Organizer pulls together public data from more than a dozen government
          sources -- safety and wage violations, labor-board filings, corporate
          ownership, finances, and more -- into a single profile for each employer,
          so organizers can quickly size up a potential target.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ClipboardList className="h-5 w-5" />
            How to read a dossier
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            Each employer has a "dossier" -- one page that gathers everything we know
            about that company. Here is what you will find on it:
          </p>
          <ol className="space-y-4">
            {DOSSIER_SECTIONS.map((s, i) => (
              <li key={s.title} className="flex gap-3">
                <span
                  className="flex h-6 w-6 flex-none items-center justify-center rounded-full text-xs font-semibold"
                  style={{ backgroundColor: '#2c2418', color: '#faf6ef' }}
                >
                  {i + 1}
                </span>
                <div>
                  <p className="font-medium">{s.title}</p>
                  <p className="text-sm text-muted-foreground">{s.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Try it yourself</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            The best way to learn it is to open a real dossier. Start from a name you
            know, or browse the curated list of organizing targets.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link to="/search" className={buttonVariants()}>
              <Search className="mr-2 h-4 w-4" />
              Search for an employer
            </Link>
            <Link to="/targets" className={buttonVariants({ variant: 'outline' })}>
              <Target className="mr-2 h-4 w-4" />
              Browse organizing targets
            </Link>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5" />
            Tell us what breaks
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            This is a beta, so rough edges are expected -- and finding them is the whole
            point. Use the <strong>Feedback</strong> button in the bottom-right corner of
            every page whenever something is broken, confusing, or looks wrong. It takes
            ten seconds and it is the most useful thing you can do while testing.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
