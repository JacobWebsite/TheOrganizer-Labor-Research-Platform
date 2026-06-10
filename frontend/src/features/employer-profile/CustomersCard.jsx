import { useState } from 'react'
import { Users2, AlertTriangle, Loader2, ExternalLink } from 'lucide-react'
import { useMasterCustomers } from '@/shared/api/profile'
import { RelationshipBody } from './RelationshipBody'

// 24Q-19: CustomersCard. Surfaces named customers extracted from this
// employer's 10-K filings via text mining. Closes Q19 Customers (was
// Missing). Top 10 by confidence, "view all" expands to 20.
//
// Mirrors SuppliersCard chrome. Linked rows (child_master_id != null)
// navigate to that master's profile via plain <a href>; unmatched
// rows render as plain text.
export function CustomersCard({ masterId }) {
  const [expanded, setExpanded] = useState(false)
  const { data, isLoading, isError, refetch } = useMasterCustomers(masterId)

  return (
    <RelationshipBody
      icon={Users2}
      title="Customers"
      data={data}
      isLoading={isLoading}
      isError={isError}
      onRetry={refetch}
      expanded={expanded}
      onToggle={() => setExpanded((v) => !v)}
      emptyText="No customer mentions found in recent 10-K filings."
      caveatText="Customers named in this employer's 10-K filings (text-mined). Linked names route to that company's profile; unmatched names appear as plain text."
      LoaderIcon={Loader2}
      AlertIcon={AlertTriangle}
      LinkIcon={ExternalLink}
    />
  )
}
