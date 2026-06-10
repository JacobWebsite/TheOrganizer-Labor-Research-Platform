import { useState } from 'react'
import { Package, AlertTriangle, Loader2, ExternalLink } from 'lucide-react'
import { useMasterSuppliers } from '@/shared/api/profile'
import { RelationshipBody } from './RelationshipBody'

// 24Q-16: SuppliersCard. Surfaces named suppliers extracted from this
// employer's 10-K filings via text mining. Closes Q16 Suppliers (was
// Missing). Top 10 by confidence, "view all" expands to 20.
//
// Mirrors LobbyingCard chrome (CollapsibleCard wrapper, minimal table,
// match-confidence chips). Linked rows (child_master_id != null)
// navigate to that master's profile via plain <a href>; unmatched rows
// render as plain text. Source attribution lives in the footer along
// with the most-recent filing date.
export function SuppliersCard({ masterId }) {
  const [expanded, setExpanded] = useState(false)
  const { data, isLoading, isError, refetch } = useMasterSuppliers(masterId)

  return (
    <RelationshipBody
      icon={Package}
      title="Suppliers"
      data={data}
      isLoading={isLoading}
      isError={isError}
      onRetry={refetch}
      expanded={expanded}
      onToggle={() => setExpanded((v) => !v)}
      emptyText="No supplier mentions found in recent 10-K filings."
      caveatText="Suppliers named in this employer's 10-K filings (text-mined). Linked names route to that company's profile; unmatched names appear as plain text."
      LoaderIcon={Loader2}
      AlertIcon={AlertTriangle}
      LinkIcon={ExternalLink}
    />
  )
}
