/** 100 little people; `filled` of them highlighted. Makes "about 18 in 100" something you can see. */
export function PeopleGrid({ filled, label }: { filled: number; label: string }) {
  const n = Math.max(0, Math.min(100, Math.round(filled)))
  return (
    <figure className="space-y-2">
      <svg viewBox="0 0 200 200" role="img" aria-label={label} className="mx-auto w-full max-w-[220px] md:max-w-[260px]">
        {Array.from({ length: 100 }).map((_, i) => {
          const cx = 10 + (i % 10) * 20
          const cy = 10 + Math.floor(i / 10) * 20
          const on = i < n
          const fill = on ? 'var(--primary)' : 'var(--border)'
          return (
            <g key={i} fill={fill}>
              <circle cx={cx} cy={cy - 3.5} r={3.4} />
              <path d={`M${cx - 5} ${cy + 7.5} q0 -8 5 -8 t5 8 z`} />
            </g>
          )
        })}
      </svg>
      <figcaption className="text-center text-xs text-muted-foreground">{label}</figcaption>
    </figure>
  )
}
