import { ConfidenceDots } from '@/shared/components/ConfidenceDots'

function formatValue(value, valueJson) {
  if (valueJson != null) {
    if (Array.isArray(valueJson)) {
      if (valueJson.length === 0) return '-'
      if (typeof valueJson[0] === 'string') return valueJson.join(', ')
      if (typeof valueJson[0] === 'object') {
        const preview = Object.entries(valueJson[0]).map(([k, v]) => `${k}: ${v}`).join(', ')
        return `${valueJson.length} record(s) — ${preview}`
      }
      return valueJson.join(', ')
    }
    if (typeof valueJson === 'object') {
      return Object.entries(valueJson).map(([k, v]) => `${k}: ${v}`).join(', ')
    }
  }
  return value || '-'
}

function confidenceBorder(confidence) {
  if (confidence == null) return 'border-l-[#d9cebb]'
  if (confidence >= 0.7) return 'border-l-[#3a7d44]'
  if (confidence >= 0.4) return 'border-l-[#c78c4e]'
  return 'border-l-[#d9cebb]'
}

export function FactRow({ fact }) {
  const displayName = fact.display_name || fact.attribute_name
  const value = formatValue(fact.attribute_value, fact.attribute_value_json)

  return (
    <tr className={`border-b last:border-0 border-l-4 ${confidenceBorder(fact.confidence)} bg-[#f5f0e8]`}>
      <td className="px-3 py-1.5 text-sm font-medium whitespace-nowrap">{displayName}</td>
      <td className="px-3 py-1.5 text-sm">{value}</td>
      <td className="px-3 py-1.5 text-[11px] text-[#8a7e6d] whitespace-nowrap">{fact.source_name || '-'}</td>
      <td className="px-3 py-1.5">
        <ConfidenceDots confidence={fact.confidence} />
      </td>
      <td className="px-3 py-1.5 text-[11px] text-[#8a7e6d] whitespace-nowrap">{fact.as_of_date || '-'}</td>
    </tr>
  )
}
