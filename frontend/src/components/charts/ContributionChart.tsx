import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Contribution } from '@/types/api'

const UP = 'var(--chart-5)'
const DOWN = 'var(--chart-2)'

/** Bars: red = pushed the result up, green = pulled it down. Uses everyday names for each answer. */
export function ContributionChart({ data, height }: { data: Contribution[]; height?: number }) {
  const rows = data.map((c) => ({
    ...c,
    name: c.plain_label ? `${c.plain_label}: ${c.plain_value ?? c.value ?? ''}` : c.label,
  }))
  return (
    <div>
      <ResponsiveContainer width="100%" height={height ?? Math.max(180, rows.length * 30 + 40)}>
        <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }} />
          <YAxis type="category" dataKey="name" width={250} tick={{ fontSize: 11, fill: 'var(--foreground)' }} />
          <ReferenceLine x={0} stroke="var(--muted-foreground)" />
          <Tooltip
            contentStyle={{ borderRadius: 8, border: '1px solid var(--border)', fontSize: 12 }}
            formatter={(v: number) => [v.toFixed(3), 'Effect on the result']}
          />
          <Bar dataKey="shap_value" radius={3}>
            {rows.map((r) => (
              <Cell key={r.feature} fill={r.shap_value >= 0 ? UP : DOWN} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: UP }} /> Pushed the result up
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: DOWN }} /> Pulled the result down
        </span>
      </div>
    </div>
  )
}
