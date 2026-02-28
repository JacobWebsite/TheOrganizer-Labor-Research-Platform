export function MiniStat({ label, value, sub, accent }) {
  return (
    <div
      className="bg-[#faf6ef] border border-[#d9cebb] rounded px-4 py-3 flex-1 min-w-[120px]"
      style={accent ? { borderTop: `3px solid ${accent}` } : undefined}
    >
      <p className="text-[10px] uppercase tracking-[1px] text-[#8a7e6d]">{label}</p>
      <p className="font-editorial text-[22px] font-bold text-[#2c2418] leading-tight mt-0.5">
        {value ?? '--'}
      </p>
      {sub && (
        <p className="text-[11px] text-[#8a7e6d] mt-0.5">{sub}</p>
      )}
    </div>
  )
}
