import { ConfidenceDots } from '@/shared/components/ConfidenceDots'

function formatValue(value, valueJson) {
  if (valueJson != null) {
    if (Array.isArray(valueJson)) return valueJson.join(', ')
    if (typeof valueJson === 'object') return JSON.stringify(valueJson)
  }
  return value || '-'
}

export function FactRow({ fact }) {
  const displayName = fact.display_name || fact.attribute_name
  const value = formatValue(fact.attribute_value, fact.attribute_value_json)

  return (
    <tr className="border-b last:border-0">
      <td className="px-3 py-1.5 text-sm font-medium whitespace-nowrap">{displayName}</td>
      <td className="px-3 py-1.5 text-sm">{value}</td>
      <td className="px-3 py-1.5 text-sm text-muted-foreground whitespace-nowrap">{fact.source_name || '-'}</td>
      <td className="px-3 py-1.5">
        <ConfidenceDots confidence={fact.confidence} />
      </td>
      <td className="px-3 py-1.5 text-sm text-muted-foreground whitespace-nowrap">{fact.as_of_date || '-'}</td>
    </tr>
  )
}
