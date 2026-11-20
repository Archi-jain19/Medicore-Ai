import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { Info, Scale } from 'lucide-react'
import { ContributionChart } from '@/components/charts/ContributionChart'
import { ChartCard, EmptyState, ErrorState, LoadingGrid, PageHeader } from '@/components/common'
import { PatientForm } from '@/components/PatientForm'
import { Alert } from '@/components/ui/alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useApi } from '@/hooks/useApi'
import { api, errorCode, errorMessage } from '@/services/api'
import type { ExplanationResult, PatientInput, ShapGlobal } from '@/types/api'
import { num, pct } from '@/utils/format'

const axis = { fontSize: 11, fill: 'var(--muted-foreground)' }
const tooltipStyle = { borderRadius: 8, border: '1px solid var(--border)', fontSize: 12 }

/** Blue (low feature value) → red (high feature value), like SHAP's summary plot. */
function valueColor(p: number | null) {
  if (p == null) return 'var(--muted-foreground)'
  const hue = 240 - p * 225
  return `oklch(0.62 0.16 ${hue})`
}

function Beeswarm({ g, top = 12 }: { g: ShapGlobal; top?: number }) {
  const feats = g.features.slice(0, top)
  const points = useMemo(() => {
    let seed = 7
    const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647) - 0.5
    return feats.flatMap((f, i) =>
      f.points.map((p) => ({ x: p.shap, y: feats.length - i + rand() * 0.55, pct: p.value_pct, feature: f.plain_label ?? f.label })),
    )
  }, [feats])
  return (
    <div>
      <ResponsiveContainer width="100%" height={top * 34 + 40}>
        <ScatterChart margin={{ left: 8, right: 16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
          <XAxis dataKey="x" type="number" tick={axis} name="SHAP" />
          <YAxis
            dataKey="y"
            type="number"
            domain={[0.4, feats.length + 0.6]}
            ticks={feats.map((_, i) => feats.length - i)}
            tickFormatter={(v) => feats[feats.length - v]?.plain_label ?? ''}
            width={200}
            tick={{ fontSize: 11, fill: 'var(--foreground)' }}
          />
          <ZAxis range={[10, 10]} />
          <ReferenceLine x={0} stroke="var(--muted-foreground)" />
          <Tooltip
            contentStyle={tooltipStyle}
            content={({ payload }) => {
              const d = payload?.[0]?.payload as { x: number; pct: number | null; feature: string } | undefined
              if (!d) return null
              return (
                <div className="rounded-md border bg-card px-2 py-1 text-xs shadow">
                  <p className="font-medium">{d.feature}</p>
                  <p>Effect {d.x.toFixed(3)}</p>
                  {d.pct != null && <p>Their value was higher than {pct(d.pct, 0)} of people</p>}
                </div>
              )
            }}
          />
          <Scatter data={points}>
            {points.map((p, i) => (
              <Cell key={i} fill={valueColor(p.pct)} fillOpacity={0.7} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
        <span>Low value</span>
        <span className="h-2 w-28 rounded-full" style={{ background: 'linear-gradient(90deg, oklch(0.62 0.16 240), oklch(0.62 0.16 15))' }} />
        <span>High value</span>
      </div>
    </div>
  )
}

export default function Explainability() {
  const { data: g, error, code, reload } = useApi<ShapGlobal>('/ml/feature-importance')
  const [local, setLocal] = useState<ExplanationResult | null>(null)
  const [localErr, setLocalErr] = useState<{ msg: string; code?: string } | null>(null)

  const explain = async (v: PatientInput) => {
    setLocalErr(null)
    try {
      const { data } = await api.post<ExplanationResult>('/ml/explain', v)
      setLocal(data)
    } catch (e) {
      setLocalErr({ msg: errorMessage(e), code: errorCode(e) })
    }
  }

  return (
    <>
      <PageHeader
        title="What affects the Health Check result?"
        description="See which of your answers matter most to the Health Check, and why a set of answers gives the result it does."
      />
      <Alert variant="info" className="mb-6">
        <Scale />
        <span className="text-sm">
          This shows which answers the Health Check pays most attention to. It is based on patterns in a 2015 US health survey, so it{' '}
          <strong>does not prove that any of these things cause diabetes</strong>. Some answers are related to each other (like weight and BMI),
          so they can share the credit.
        </span>
      </Alert>

      {error ? (
        <ErrorState message={error} code={code} onRetry={reload} />
      ) : !g ? (
        <LoadingGrid cards={2} />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          <ChartCard
            title="Which answers matter most overall"
            description={`Longer bar = the answer has more effect on the result. Based on ${g.n_samples.toLocaleString()} people the Health Check had not seen before.`}
            footer="Technical note: average absolute SHAP value, on the model's log-odds scale."
          >
            <ResponsiveContainer width="100%" height={12 * 30 + 40}>
              <BarChart data={g.features.slice(0, 12)} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                <XAxis type="number" tick={axis} />
                <YAxis type="category" dataKey="plain_label" width={230} tick={{ fontSize: 11, fill: 'var(--foreground)' }} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [v.toFixed(3), 'Average effect']} />
                <Bar dataKey="mean_abs_shap" fill="var(--chart-1)" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
          <ChartCard
            title="How answers pushed results, person by person"
            description="Each dot is one person in the survey. Dots to the right pushed their result up, dots to the left pulled it down. Red means a high value for that answer, blue a low one."
          >
            <Beeswarm g={g} />
          </ChartCard>
        </div>
      )}

      <h2 className="mt-8 mb-1 text-lg font-semibold text-primary">Try it with a set of answers</h2>
      <p className="mb-3 text-sm text-muted-foreground">Answer the questions (or use the example answers) to see what pushed that result up or down.</p>
      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Your answers</CardTitle>
          </CardHeader>
          <CardContent>
            <PatientForm onSubmit={explain} submitLabel="Show what matters" />
          </CardContent>
        </Card>
        <div className="space-y-4">
          {localErr ? (
            <ErrorState message={localErr.msg} code={localErr.code} />
          ) : local ? (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Why these answers give about {Math.round(local.probability * 100)} in 100</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <p className="leading-relaxed">{local.explanation}</p>
                  <details className="text-xs text-muted-foreground">
                    <summary className="cursor-pointer">Technical detail</summary>
                    <p className="mt-1">
                      Baseline (average model output) {num(local.base_value)} + sum of contributions{' '}
                      {num(local.contributions.reduce((s, c) => s + c.shap_value, 0))} ={' '}
                      {num(local.base_value + local.contributions.reduce((s, c) => s + c.shap_value, 0))} ({local.output_space}).
                    </p>
                  </details>
                </CardContent>
              </Card>
              <ChartCard title="How much each answer mattered" footer={local.note}>
                <ContributionChart data={local.contributions} />
              </ChartCard>
            </>
          ) : (
            <Card>
              <CardContent className="p-5">
                <EmptyState icon={Info} title="Nothing to show yet" body="Fill in the answers and press the button to see what pushed the result up or down." />
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
