import { ArrowDown, ArrowUp } from 'lucide-react'
import type { Contribution } from '@/types/api'

function Row({ c, up }: { c: Contribution; up: boolean }) {
  return (
    <li className="flex items-start gap-2.5 rounded-lg border bg-card p-3 text-sm">
      <span className={up ? 'mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-destructive/10 text-destructive' : 'mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-success/15 text-success'}>
        {up ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" />}
      </span>
      <span>
        <span className="block text-muted-foreground">{c.plain_label ?? c.label}</span>
        <span className="font-medium">{c.plain_value ?? String(c.value ?? '')}</span>
      </span>
    </li>
  )
}

/** "What mattered most" in plain words: the answers that raised and lowered the result. */
export function FactorList({ data, perSide = 3 }: { data: Contribution[]; perSide?: number }) {
  const up = data.filter((c) => c.direction === 'increases').slice(0, perSide)
  const down = data.filter((c) => c.direction === 'decreases').slice(0, perSide)
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="space-y-2">
        <p className="text-sm font-semibold">Pushed your result up</p>
        {up.length ? (
          <ul className="space-y-2">
            {up.map((c) => (
              <Row key={c.feature} c={c} up />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Nothing in your answers raised it much.</p>
        )}
      </div>
      <div className="space-y-2">
        <p className="text-sm font-semibold">Pulled your result down</p>
        {down.length ? (
          <ul className="space-y-2">
            {down.map((c) => (
              <Row key={c.feature} c={c} up={false} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Nothing in your answers lowered it much.</p>
        )}
      </div>
    </div>
  )
}
