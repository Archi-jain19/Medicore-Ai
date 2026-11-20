import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import { Info } from 'lucide-react'
import { ChartCard, ErrorState, LoadingGrid, PageHeader } from '@/components/common'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/misc'
import { useApi } from '@/hooks/useApi'
import { cn } from '@/lib/utils'
import type { ClusterResult, ModelPerformance } from '@/types/api'
import { int, num, pct } from '@/utils/format'

const axis = { fontSize: 11, fill: 'var(--muted-foreground)' }
const tooltipStyle = { borderRadius: 8, border: '1px solid var(--border)', fontSize: 12 }
const SEG_COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)']

// ---------------------------------------------------------------- Performance
function ConfusionMatrix({ cm }: { cm: { tn: number; fp: number; fn: number; tp: number } }) {
  const total = cm.tn + cm.fp + cm.fn + cm.tp
  const cell = (v: number, label: string, tone: string) => (
    <div className={cn('rounded-lg p-3 text-center', tone)}>
      <p className="text-lg font-semibold tabular-nums">{int(v)}</p>
      <p className="text-[11px] text-muted-foreground">
        {label} · {pct(v / total)}
      </p>
    </div>
  )
  return (
    <div className="grid grid-cols-[auto_1fr_1fr] items-center gap-2 text-xs">
      <span />
      <span className="text-center text-muted-foreground">Predicted negative</span>
      <span className="text-center text-muted-foreground">Predicted positive</span>
      <span className="text-muted-foreground">Actual neg.</span>
      {cell(cm.tn, 'True negative', 'bg-secondary')}
      {cell(cm.fp, 'False positive', 'bg-warning/15')}
      <span className="text-muted-foreground">Actual pos.</span>
      {cell(cm.fn, 'False negative', 'bg-destructive/10')}
      {cell(cm.tp, 'True positive', 'bg-accent')}
    </div>
  )
}

export function PerformanceTab() {
  const { data, error, code, reload } = useApi<ModelPerformance>('/ml/model-performance')
  if (error) return <ErrorState message={error} code={code} onRetry={reload} />
  if (!data) return <LoadingGrid />
  const sel = data.models[data.selected_model]
  const rows = Object.entries(data.models).sort((a, b) => b[1].validation.pr_auc - a[1].validation.pr_auc)
  const compare = rows.map(([k, m]) => ({
    key: k,
    name: m.display_name.replace(/ \(.*\)/, ''),
    'ROC-AUC': m.test.roc_auc,
    'PR-AUC': m.test.pr_auc,
    Recall: m.test.at_threshold.recall,
    Precision: m.test.at_threshold.precision,
  }))
  const curves = data.selected.curves_test
  const bs = data.selected.bootstrap_test

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>In plain words</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="text-base">{data.plain_summary}</p>
          <p className="text-muted-foreground">
            So the Health Check is useful as a first nudge to ask about a blood sugar test, but it is not a test. Many people it flags are fine,
            and some people with diabetes are missed. It was built from a 2015 US health survey and has not been checked in clinics.
          </p>
        </CardContent>
      </Card>

      <h2 className="pt-2 text-lg font-semibold text-primary">The technical details</h2>
      <Alert variant="info">
        <Info />
        <div className="space-y-1 text-sm">
          <p>
            <span className="font-medium">Selected: {sel.display_name}.</span> Chosen by {data.selection_criterion}. Threshold rule:{' '}
            {data.threshold_policy}. Every metric below was measured on the untouched test split ({int(data.splits.test.rows)} respondents,
            prevalence {pct(data.splits.test.positive_rate)}).
          </p>
          <p className="text-xs text-muted-foreground">
            Test ROC-AUC 95% bootstrap CI [{bs.roc_auc_95ci.join(', ')}], PR-AUC CI [{bs.pr_auc_95ci.join(', ')}] ({bs.n_bootstrap} resamples).
          </p>
        </div>
      </Alert>

      <ChartCard title="Model comparison (test split)" description="Recall and precision are measured at each model's own validation-selected threshold">
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={compare}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis dataKey="name" tick={axis} interval={0} angle={-15} textAnchor="end" height={50} />
            <YAxis tick={axis} domain={[0, 1]} />
            <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => v.toFixed(3)} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="ROC-AUC" fill="var(--chart-1)" radius={[3, 3, 0, 0]} />
            <Bar dataKey="PR-AUC" fill="var(--chart-2)" radius={[3, 3, 0, 0]} />
            <Bar dataKey="Recall" fill="var(--chart-3)" radius={[3, 3, 0, 0]} />
            <Bar dataKey="Precision" fill="var(--chart-4)" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <Card>
        <CardHeader>
          <CardTitle>All candidates</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <THead>
              <TR>
                <TH>Model</TH>
                <TH>CV PR-AUC</TH>
                <TH>Val PR-AUC</TH>
                <TH>Test ROC-AUC</TH>
                <TH>Test PR-AUC</TH>
                <TH>Recall</TH>
                <TH>Precision</TH>
                <TH>Specificity</TH>
                <TH>F2</TH>
                <TH>Brier</TH>
                <TH>Train rows</TH>
              </TR>
            </THead>
            <TBody>
              {rows.map(([k, m]) => (
                <TR key={k} className={k === data.selected_model ? 'bg-accent/50' : ''}>
                  <TD className="font-medium">
                    {m.display_name} {k === data.selected_model && <Badge variant="teal">selected</Badge>}
                  </TD>
                  <TD className="tabular-nums">
                    {num(m.cv_pr_auc_mean)} ± {num(m.cv_pr_auc_std)}
                  </TD>
                  <TD className="tabular-nums">{num(m.validation.pr_auc)}</TD>
                  <TD className="tabular-nums">{num(m.test.roc_auc)}</TD>
                  <TD className="tabular-nums">{num(m.test.pr_auc)}</TD>
                  <TD className="tabular-nums">{pct(m.test.at_threshold.recall)}</TD>
                  <TD className="tabular-nums">{pct(m.test.at_threshold.precision)}</TD>
                  <TD className="tabular-nums">{pct(m.test.at_threshold.specificity)}</TD>
                  <TD className="tabular-nums">{num(m.test.at_threshold.f2)}</TD>
                  <TD className="tabular-nums">{num(m.test.brier)}</TD>
                  <TD className="tabular-nums">{int(m.train_rows)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <ChartCard title="ROC curve" description={`${sel.display_name} · AUC ${num(sel.test.roc_auc)}`}>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={curves.roc}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="fpr" type="number" domain={[0, 1]} tick={axis} label={{ value: 'False positive rate', position: 'insideBottom', offset: -2, fontSize: 11 }} />
              <YAxis domain={[0, 1]} tick={axis} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => v.toFixed(3)} />
              <Area dataKey="tpr" stroke="var(--chart-1)" fill="var(--chart-1)" fillOpacity={0.12} strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Precision–recall curve" description={`AP ${num(sel.test.pr_auc)} · baseline ${pct(sel.test.prevalence)}`}>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={curves.pr}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="recall" type="number" domain={[0, 1]} tick={axis} label={{ value: 'Recall', position: 'insideBottom', offset: -2, fontSize: 11 }} />
              <YAxis domain={[0, 1]} tick={axis} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => v.toFixed(3)} />
              <Line dataKey="precision" stroke="var(--chart-2)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Calibration" description="Observed rate vs. predicted probability (10 quantile bins)">
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={curves.calibration}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="mean_predicted" type="number" domain={[0, 'dataMax']} tick={axis} tickFormatter={(v) => pct(v, 0)} />
              <YAxis tick={axis} tickFormatter={(v) => pct(v, 0)} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => pct(v)} />
              <Line dataKey="mean_predicted" stroke="var(--muted-foreground)" strokeDasharray="4 4" dot={false} name="Perfect calibration" />
              <Line dataKey="observed_rate" stroke="var(--chart-1)" strokeWidth={2} name="Observed" />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Confusion matrix (test)"
          description={`At threshold ${num(sel.test.at_threshold.threshold)}. False negatives are at-risk respondents the model missed.`}
        >
          <ConfusionMatrix cm={sel.test.at_threshold.confusion_matrix} />
        </ChartCard>
        <ChartCard title="Threshold trade-off (validation)" description="Lowering the threshold catches more cases (recall) but adds false positives">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data.selected.threshold_table_val}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="threshold" tick={axis} />
              <YAxis domain={[0, 1]} tick={axis} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => v.toFixed(3)} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line dataKey="recall" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
              <Line dataKey="precision" stroke="var(--chart-2)" strokeWidth={2} dot={false} />
              <Line dataKey="specificity" stroke="var(--chart-4)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- Segments
export function SegmentsTab() {
  const { data, error, code, reload } = useApi<ClusterResult>('/ml/clusters')
  if (error) return <ErrorState message={error} code={code} onRetry={reload} />
  if (!data) return <LoadingGrid />
  return (
    <div className="space-y-4">
      <Alert variant="info">
        <Info />
        <span className="text-sm">{data.note}</span>
      </Alert>
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Choosing k" description={`${data.choice_rule}. Elbow at k=${data.elbow_k}; chosen k=${data.chosen_k}.`}>
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={data.selection}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="k" tick={axis} />
              <YAxis yAxisId="l" tick={axis} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
              <YAxis yAxisId="r" orientation="right" tick={axis} domain={[0, 'auto']} />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line yAxisId="l" dataKey="inertia" stroke="var(--chart-1)" strokeWidth={2} name="Inertia (elbow)" />
              <Line yAxisId="r" dataKey="silhouette" stroke="var(--chart-2)" strokeWidth={2} name="Silhouette" />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard
          title="PCA projection"
          description={`1,500 sampled respondents · PC1 ${pct(data.pca_explained_variance[0])}, PC2 ${pct(data.pca_explained_variance[1])} of variance`}
        >
          <ResponsiveContainer width="100%" height={250}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="x" type="number" tick={axis} name="PC1" />
              <YAxis dataKey="y" type="number" tick={axis} name="PC2" />
              <ZAxis range={[12, 12]} />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {data.segments.map((s) => (
                <Scatter
                  key={s.id}
                  name={s.name}
                  data={data.pca_points.filter((p) => p.segment === s.id)}
                  fill={SEG_COLORS[s.id % SEG_COLORS.length]}
                  fillOpacity={0.6}
                />
              ))}
            </ScatterChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data.segments.map((s) => (
          <Card key={s.id}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <span className="size-2.5 rounded-full" style={{ background: SEG_COLORS[s.id % SEG_COLORS.length] }} />
                  {s.name}
                </CardTitle>
                <Badge variant="outline">{pct(s.share)} of respondents</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
                {s.description.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
              <p>
                Observed prediabetes/diabetes rate: <span className="font-medium">{pct(s.observed_diabetes_rate)}</span>
              </p>
              <div className="grid grid-cols-3 gap-2 text-xs">
                {Object.entries(s.feature_means).map(([k, v]) => (
                  <div key={k} className="rounded-md bg-secondary px-2 py-1.5">
                    <p className="truncate text-muted-foreground">{k}</p>
                    <p className="font-medium tabular-nums">{v.toFixed(2)}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}


export function AccuracyPage() {
  return (
    <>
      <PageHeader
        title="How well does the Health Check work?"
        description="The numbers behind the Health Check, measured on about 50,000 people the method had never seen before. This page is for people who like the details."
      />
      <PerformanceTab />
    </>
  )
}

export function GroupsPage() {
  return (
    <>
      <PageHeader
        title="Patterns in the data"
        description="We grouped the survey respondents by how similar their answers were. These groups only describe patterns. They are not medical conditions."
      />
      <SegmentsTab />
    </>
  )
}
