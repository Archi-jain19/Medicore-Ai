import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, Info } from 'lucide-react'
import { ChartCard, ErrorState, LoadingGrid, PageHeader } from '@/components/common'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/misc'
import { useApi } from '@/hooks/useApi'
import { num, pct } from '@/utils/format'

interface StrategyResult {
  retrieval: Record<string, number>
  generation: { measured: boolean; reason?: string; [k: string]: unknown }
  by_type: Record<string, number | null>
  questions: { id: string; type: string; answerable: boolean; sufficient: boolean; retrieved_docs: string[]; hit?: number; rr?: number }[]
}

interface RagEvaluation {
  generated_at: string
  k: number
  benchmark: { n: number; answerable: number; unanswerable: number; labelling_protocol: string }
  knowledge_base: { documents_indexed: number; chunks: number; documents_by_source: Record<string, number>; embedding_model: string }
  ranking_config: Record<string, unknown>
  strategies: Record<'basic' | 'reranked' | 'adaptive', StrategyResult>
  caveats: string[]
}

const axis = { fontSize: 11, fill: 'var(--muted-foreground)' }
const tooltipStyle = { borderRadius: 8, border: '1px solid var(--border)', fontSize: 12 }
const LABEL: Record<string, string> = { basic: 'Basic vector RAG', reranked: 'Reranked RAG', adaptive: 'Adaptive RAG' }
const COLORS: Record<string, string> = { basic: 'var(--chart-3)', reranked: 'var(--chart-2)', adaptive: 'var(--chart-1)' }

export default function RagEvaluation() {
  const { data, error, reload } = useApi<RagEvaluation>('/rag/evaluation')
  if (error) {
    return (
      <>
        <PageHeader title="How we check our answers" />
        <ErrorState message={error} onRetry={reload} />
      </>
    )
  }
  if (!data) return <LoadingGrid />
  const k = data.k
  const strategies = Object.keys(data.strategies) as (keyof RagEvaluation['strategies'])[]
  const metrics = [`precision@${k}`, `recall@${k}`, `hit@${k}`, 'mrr']
  const chart = metrics.map((m) => ({
    metric: m.toUpperCase().replace('@', '@'),
    ...Object.fromEntries(strategies.map((s) => [s, data.strategies[s].retrieval[m]])),
  }))
  const types = Object.keys(data.strategies.basic.by_type)
  const typeChart = types.map((t) => ({ type: t.replace('_', ' '), ...Object.fromEntries(strategies.map((s) => [s, data.strategies[s].by_type[t]])) }))
  const gen = data.strategies.adaptive.generation
  const unans = data.strategies.adaptive.questions.filter((q) => !q.answerable)

  return (
    <>
      <PageHeader
        title="How we check our answers"
        description={`We test how well our library finds the right sources. We asked ${data.benchmark.answerable} health questions that our sources can answer, and ${data.benchmark.unanswerable} that they cannot, then checked the results by hand. This page is for people who like the details.`}
      />

      <Card className="mb-4">
        <CardHeader>
          <CardTitle>In plain words</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="text-base">
            For the questions our library can answer, we found at least one correct source in the top results every time (
            {pct(data.strategies.adaptive.retrieval[`hit@${data.k}`], 0)}), and the most relevant source was usually first or second.
          </p>
          <p className="text-muted-foreground">
            We also asked questions that have nothing to do with health. We correctly said “I could not find a reliable answer” for{' '}
            {Math.round((data.strategies.adaptive.retrieval.abstention_accuracy_unanswerable ?? 0) * data.benchmark.unanswerable)} of{' '}
            {data.benchmark.unanswerable}. The one we got wrong was a medical question about a topic our library does not cover. These
            are small tests, so please treat the numbers as a rough guide.
          </p>
        </CardContent>
      </Card>
      <Alert variant="info" className="mb-4">
        <Info />
        <div className="space-y-1 text-sm">
          <p>These numbers were measured on {new Date(data.generated_at).toLocaleDateString()}. We did not adjust the system to do well on this test.</p>
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer">How the test was set up</summary>
            <p className="mt-1">{data.benchmark.labelling_protocol.split('\n').join(' ')}</p>
          </details>
        </div>
      </Alert>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="How often the right sources are found" description={`Looking at the top ${k} sources for each question. Higher is better.`}>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chart}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="metric" tick={axis} />
              <YAxis domain={[0, 1]} tick={axis} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => v.toFixed(3)} />
              <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v) => LABEL[v] ?? v} />
              {strategies.map((s) => (
                <Bar key={s} dataKey={s} fill={COLORS[s]} radius={[3, 3, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="By type of question" description="How much of the right material was found for each kind of question">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={typeChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="type" tick={axis} interval={0} angle={-20} textAnchor="end" height={50} />
              <YAxis domain={[0, 1]} tick={axis} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => v.toFixed(3)} />
              {strategies.map((s) => (
                <Bar key={s} dataKey={s} fill={COLORS[s]} radius={[3, 3, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>The detailed numbers</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <THead>
              <TR>
                <TH>Strategy</TH>
                <TH>P@{k}</TH>
                <TH>R@{k}</TH>
                <TH>Hit@{k}</TH>
                <TH>MRR</TH>
                <TH>Avg passages</TH>
                <TH>Unanswerable refused</TH>
                <TH>False refusals</TH>
                <TH>Median latency</TH>
              </TR>
            </THead>
            <TBody>
              {strategies.map((s) => {
                const r = data.strategies[s].retrieval
                return (
                  <TR key={s}>
                    <TD className="font-medium">{LABEL[s]}</TD>
                    <TD className="tabular-nums">{num(r[`precision@${k}`])}</TD>
                    <TD className="tabular-nums">{num(r[`recall@${k}`])}</TD>
                    <TD className="tabular-nums">{num(r[`hit@${k}`])}</TD>
                    <TD className="tabular-nums">{num(r.mrr)}</TD>
                    <TD className="tabular-nums">{num(r.avg_passages_returned, 2)}</TD>
                    <TD className="tabular-nums">{pct(r.abstention_accuracy_unanswerable, 0)}</TD>
                    <TD className="tabular-nums">{pct(r.false_abstention_rate_answerable, 0)}</TD>
                    <TD className="tabular-nums">{r.median_latency_ms} ms</TD>
                  </TR>
                )
              })}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Quality of the written answers</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {gen.measured ? (
              <Table>
                <THead>
                  <TR>
                    <TH>Strategy</TH>
                    <TH>Faithfulness</TH>
                    <TH>Answer relevance</TH>
                    <TH>Citation correctness</TH>
                    <TH>Context utilisation</TH>
                  </TR>
                </THead>
                <TBody>
                  {strategies.map((s) => {
                    const g = data.strategies[s].generation as Record<string, number>
                    return (
                      <TR key={s}>
                        <TD className="font-medium">{LABEL[s]}</TD>
                        <TD>{num(g.faithfulness)}</TD>
                        <TD>{num(g.answer_relevance)}</TD>
                        <TD>{num(g.citation_correctness)}</TD>
                        <TD>{num(g.context_utilisation)}</TD>
                      </TR>
                    )
                  })}
                </TBody>
              </Table>
            ) : (
              <Alert variant="warning">
                <AlertTriangle />
                <span>
                  <strong>Not measured yet.</strong> We have not yet tested how well the written answers match their sources. This will appear here
                  once we have.
                </span>
              </Alert>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Questions we should not answer</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {unans.map((q) => (
                <li key={q.id} className="flex items-start justify-between gap-3">
                  <span>
                    <span className="font-mono text-xs text-muted-foreground">{q.id}</span> {q.type.includes('medical') ? 'a medical topic not in our library' : 'not about health'}
                    {!q.sufficient ? null : <span className="block text-xs text-destructive">We gave an answer using an unrelated source.</span>}
                  </span>
                  <Badge variant={q.sufficient ? 'destructive' : 'success'}>{q.sufficient ? 'answered by mistake' : 'correctly declined'}</Badge>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <Alert variant="warning" className="mt-4">
        <AlertTriangle />
        <ul className="list-disc space-y-1 pl-4 text-sm">
          {data.caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </Alert>
    </>
  )
}
