import { useState } from 'react'
import { Flag, Download, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { FlagModal } from './FlagModal'

function exportProfileCsv(employer, scorecard) {
  const rows = [
    ['Field', 'Value'],
    ['Name', employer?.employer_name || ''],
    ['City', employer?.city || ''],
    ['State', employer?.state || ''],
    ['Workers', employer?.consolidated_workers || employer?.unit_size || ''],
    ['NAICS', employer?.naics_code || employer?.naics || ''],
    ['Union', employer?.union_name || 'None'],
    ['Score Tier', scorecard?.score_tier || ''],
    ['Weighted Score', scorecard?.weighted_score || ''],
    ['OSHA Score', scorecard?.score_osha || ''],
    ['NLRB Score', scorecard?.score_nlrb || ''],
    ['WHD Score', scorecard?.score_whd || ''],
  ]
  const csv = rows.map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${(employer?.employer_name || 'employer').replace(/[^a-z0-9]/gi, '_')}_profile.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export function ProfileActionButtons({ employer, scorecard }) {
  const [flagOpen, setFlagOpen] = useState(false)
  const [flagType, setFlagType] = useState(null)

  const employerId = employer?.employer_id || employer?.canonical_id
  if (!employerId) return null

  return (
    <>
      <div className="flex items-center gap-2 mt-4 pt-4 border-t">
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => { setFlagType(null); setFlagOpen(true) }}
        >
          <Flag className="h-3.5 w-3.5" />
          Flag as Target
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => exportProfileCsv(employer, scorecard)}
        >
          <Download className="h-3.5 w-3.5" />
          Export Data
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 text-amber-600 hover:text-amber-700"
          onClick={() => { setFlagType('DATA_QUALITY'); setFlagOpen(true) }}
        >
          <AlertTriangle className="h-3.5 w-3.5" />
          Something Looks Wrong
        </Button>
      </div>

      {flagOpen && (
        <FlagModal
          sourceType="F7"
          sourceId={employerId}
          initialFlagType={flagType}
          onClose={() => setFlagOpen(false)}
        />
      )}
    </>
  )
}
