import { Globe, Phone, Printer, Mail, MapPin, Users } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'

/**
 * Format officer text. The scraper stores officers one per line as either
 *   "First Last, Suffix (Position)"  or just  "First Last"
 * Returns an array of { name, position } objects.
 */
function parseOfficers(raw) {
  if (!raw || typeof raw !== 'string') return []
  return raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match = line.match(/^(.+?)\s*\(([^)]+)\)\s*$/)
      if (match) {
        return { name: match[1].trim(), position: match[2].trim() }
      }
      return { name: line, position: null }
    })
}

/**
 * Format a scrape-status value for display.
 */
function scrapeStatusLabel(status) {
  switch (status) {
    case 'DIRECTORY_ONLY':
      return 'Directory listing'
    case 'FETCHED':
      return 'Page fetched'
    case 'EXTRACTED':
      return 'Content extracted'
    case 'NO_WEBSITE':
      return 'No website'
    default:
      return status || 'Unknown'
  }
}

/**
 * Extract the hostname from a URL for display as the "go to website" label.
 */
function urlHostname(url) {
  if (!url) return null
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url.replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0]
  }
}

/**
 * Union web profile section. Shows data scraped from the parent union's
 * locals directory: website, contact info, mailing address, officers, and a
 * link back to the source directory page.
 *
 * Hidden entirely when the union has no matched web profile (~20% of OLMS
 * unions as of 2026-04-21).
 */
export function UnionWebProfileSection({ webProfile }) {
  if (!webProfile) return null

  const {
    website_url,
    phone,
    fax,
    email,
    address,
    officers,
    parent_union,
    source_directory_url,
    scrape_status,
  } = webProfile

  const parsedOfficers = parseOfficers(officers)
  const hasContactRow = website_url || phone || fax || email

  // Count what's actually populated so we can show an informative summary
  const populated = [
    website_url && 'website',
    phone && 'phone',
    email && 'email',
    address && 'address',
    parsedOfficers.length > 0 && 'officers',
  ].filter(Boolean)

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-lg">Union Website &amp; Contact</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Sourced from {parent_union || 'parent union'} directory
              {scrape_status ? ` \u2022 ${scrapeStatusLabel(scrape_status)}` : ''}
            </p>
          </div>
          {website_url && (
            <a
              href={website_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md border border-[#c4a86a] bg-[#c4a86a]/10 px-3 py-1.5 text-xs font-medium text-[#2c2418] hover:bg-[#c4a86a]/20 transition-colors"
            >
              <Globe className="h-3.5 w-3.5" />
              {urlHostname(website_url)}
            </a>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Contact row */}
        {hasContactRow && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
            {phone && (
              <div className="flex items-center gap-2">
                <Phone className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <a href={`tel:${phone.replace(/[^\d+]/g, '')}`} className="hover:underline">
                  {phone}
                </a>
              </div>
            )}
            {fax && (
              <div className="flex items-center gap-2">
                <Printer className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground">Fax:</span>
                <span>{fax}</span>
              </div>
            )}
            {email && (
              <div className="flex items-center gap-2">
                <Mail className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <a href={`mailto:${email}`} className="hover:underline truncate">
                  {email}
                </a>
              </div>
            )}
          </div>
        )}

        {/* Address */}
        {address && (
          <div className="flex items-start gap-2 text-sm">
            <MapPin className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
            <span className="text-[#2c2418]">{address}</span>
          </div>
        )}

        {/* Officers */}
        {parsedOfficers.length > 0 && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              <Users className="h-3.5 w-3.5" />
              Officers ({parsedOfficers.length})
            </div>
            <ul className="text-sm space-y-1 pl-5">
              {parsedOfficers.map((o, i) => (
                <li key={i} className="text-[#2c2418]">
                  {o.name}
                  {o.position && (
                    <span className="text-muted-foreground">{' \u2014 '}{o.position}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Empty state: no contact fields populated */}
        {populated.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No contact information recorded. This union's directory entry lacked contact fields.
          </p>
        )}

        {/* Source footnote */}
        {source_directory_url && (
          <p className="text-xs text-muted-foreground italic pt-2 border-t">
            Scraped from{' '}
            <a
              href={source_directory_url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline"
            >
              {urlHostname(source_directory_url)}
            </a>
          </p>
        )}
      </CardContent>
    </Card>
  )
}
