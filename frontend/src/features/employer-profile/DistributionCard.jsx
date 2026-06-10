import { useState } from 'react'
import { Truck, AlertTriangle, Loader2, ExternalLink } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Button } from '@/components/ui/button'
import { useMasterDistributionPartners } from '@/shared/api/profile'
import { RelationshipBody } from './RelationshipBody'

// 24Q-17: DistributionCard. Surfaces named distribution partners
// extracted from this employer's 10-K filings via text mining. Closes
// Q17 Distribution (was Missing). Top 10 by confidence, "view all"
// expands to 20.
//
// Mirrors SuppliersCard chrome. Linked rows (child_master_id != null)
// navigate to that master's profile via plain <a href>; unmatched
// rows render as plain text.
export function DistributionCard({ masterId }) {
  const [expanded, setExpanded] = useState(false)
  const { data, isLoading, isError, refetch } = useMasterDistributionPartners(masterId)

  return (
    <RelationshipBody
      icon={Truck}
      title="Distribution Partners"
      data={data}
      isLoading={isLoading}
      isError={isError}
      onRetry={refetch}
      expanded={expanded}
      onToggle={() => setExpanded((v) => !v)}
      emptyText="No distribution-partner mentions found in recent 10-K filings."
      caveatText="Distribution partners named in this employer's 10-K filings (text-mined). Linked names route to that company's profile; unmatched names appear as plain text."
      LoaderIcon={Loader2}
      AlertIcon={AlertTriangle}
      LinkIcon={ExternalLink}
    />
  )
}
