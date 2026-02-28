import { cn } from '@/lib/utils'

function arcPath(cx, cy, r, startAngle, endAngle) {
  const rad = (deg) => (deg * Math.PI) / 180
  const x1 = cx + r * Math.cos(rad(startAngle))
  const y1 = cy + r * Math.sin(rad(startAngle))
  const x2 = cx + r * Math.cos(rad(endAngle))
  const y2 = cy + r * Math.sin(rad(endAngle))
  const largeArc = endAngle - startAngle > 180 ? 1 : 0
  return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`
}

function gaugeColor(value) {
  if (value >= 7) return '#c23a22'
  if (value >= 4) return '#c78c4e'
  return '#d9cebb'
}

export function ScoreGauge({ value, max = 10, label, size = 54 }) {
  const cx = size / 2
  const cy = size / 2 + 2
  const r = size / 2 - 4
  const startAngle = 180
  const endAngle = 360
  const totalSweep = endAngle - startAngle

  const ratio = value != null ? Math.min(Math.max(value, 0), max) / max : 0
  const filledEnd = startAngle + totalSweep * ratio

  const bgPath = arcPath(cx, cy, r, startAngle, endAngle)
  const fillPath = value != null && ratio > 0 ? arcPath(cx, cy, r, startAngle, filledEnd) : null

  const strokeWidth = 5
  const color = value != null ? gaugeColor(value) : '#d9cebb'

  return (
    <div className="flex flex-col items-center" style={{ width: size }}>
      <svg width={size} height={size / 2 + 8} viewBox={`0 0 ${size} ${size / 2 + 8}`}>
        {/* Background arc */}
        <path
          d={bgPath}
          fill="none"
          stroke="#ede7db"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />
        {/* Filled arc */}
        {fillPath && (
          <path
            d={fillPath}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            className="transition-all duration-700 ease-out"
          />
        )}
        {/* Score value */}
        <text
          x={cx}
          y={cy - 2}
          textAnchor="middle"
          className="font-editorial font-bold fill-[#2c2418]"
          fontSize={size * 0.3}
        >
          {value != null ? Number(value).toFixed(1) : '--'}
        </text>
      </svg>
      {label && (
        <span className="text-[10px] text-[#8a7e6d] text-center leading-tight mt-0.5 truncate w-full">
          {label}
        </span>
      )}
    </div>
  )
}
