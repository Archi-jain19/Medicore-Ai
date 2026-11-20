import { useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, ClipboardList, HeartPulse, History, MapPin, MessageSquareText, ShieldAlert } from 'lucide-react'
import { ContributionChart } from '@/components/charts/ContributionChart'
import { EmptyState, ErrorState, LoadingGrid, PageHeader } from '@/components/common'
import { FactorList } from '@/components/FactorList'
import { PatientForm } from '@/components/PatientForm'
import { PeopleGrid } from '@/components/PeopleGrid'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, Tabs, TabsContent, TabsList, TabsTrigger, TBody, TD, TH, THead, TR } from '@/components/ui/misc'
import { useApi } from '@/hooks/useApi'
import { api, errorCode, errorMessage } from '@/services/api'
import type { PatientInput, PredictionHistoryItem, PredictionResult } from '@/types/api'
import { BAND_META, dateTime, pct } from '@/utils/format'

function Result({ r, onRedo }: { r: PredictionResult; onRedo: () => void }) {
  const band = BAND_META[r.risk_band]
  const filled = Math.round(r.probability * 100)
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="grid gap-6 p-6 md:grid-cols-[auto_1fr] md:items-center">
          {/* on a phone the headline comes first, then the picture */}
          <div className="order-2 md:order-1">
            <PeopleGrid filled={filled} label={`${r.chance_text} (highlighted)`} />
          </div>
          <div className="order-1 space-y-3 md:order-2">
            <Badge variant={band.variant}>{band.label}</Badge>
            <h2 className="text-2xl font-semibold text-primary">{r.headline}</h2>
            <p className="text-lg">
              <span className="font-semibold">{r.chance_text}</span> people with answers like yours said they have diabetes or prediabetes.
            </p>
            <p className="text-sm text-muted-foreground">
              For comparison, about {Math.round(r.population_base_rate * 100)} in 100 people overall said so in the survey this check is based on.
            </p>
          </div>
        </CardContent>
      </Card>

      <Alert variant={r.risk_band === 'lower' ? 'info' : 'warning'}>
        <HeartPulse />
        <div className="space-y-3">
          <p className="font-medium">What you can do next</p>
          <p className="text-sm">{r.next_step}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" asChild>
              <Link to="/locator?category=pharmacy">
                <MapPin /> Find a pharmacy or clinic near me
              </Link>
            </Button>
            <Button size="sm" variant="outline" asChild>
              <Link to="/assistant?q=What%20is%20prediabetes%3F">
                <MessageSquareText /> Learn about diabetes
              </Link>
            </Button>
          </div>
        </div>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle>What mattered most in your answers</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <FactorList data={r.top_contributions} />
          <p className="text-xs text-muted-foreground">These are patterns in the survey data. They do not prove what is causing anything.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Please remember</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1.5 pl-5 text-sm">
            {r.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <details className="rounded-xl border bg-card px-5 py-3 text-sm">
        <summary className="cursor-pointer font-medium">Show the technical details</summary>
        <div className="mt-3 space-y-3">
          <p className="text-muted-foreground">
            Worked out with {r.algorithm} (version {r.model_version}). The exact calibrated chance was {pct(r.probability)}. Bars show how much each answer moved the
            result, as measured by a method called SHAP.
          </p>
          <ContributionChart data={r.top_contributions} />
        </div>
      </details>

      <Button variant="outline" onClick={onRedo}>
        Start a new check
      </Button>
    </div>
  )
}

function CheckTab({ onSaved }: { onSaved: () => void }) {
  const [result, setResult] = useState<PredictionResult | null>(null)
  const [error, setError] = useState<{ msg: string; code?: string } | null>(null)
  const top = useRef<HTMLDivElement>(null)

  const submit = async (v: PatientInput) => {
    setError(null)
    try {
      const { data } = await api.post<PredictionResult>('/ml/predict', v)
      setResult(data)
      onSaved()
      requestAnimationFrame(() => top.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' }))
    } catch (e) {
      setError({ msg: errorMessage(e), code: errorCode(e) })
    }
  }

  return (
    <div ref={top} className="scroll-mt-4">
      {error && (
        <div className="mb-4">
          <ErrorState message={error.msg} code={error.code} />
        </div>
      )}
      {result ? (
        <Result r={result} onRedo={() => setResult(null)} />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Answer a few questions</CardTitle>
            <p className="text-sm text-muted-foreground">
              It takes about 2 minutes. Your answers are compared with a large US health survey to show how people with similar answers
              responded about diabetes. Nobody else sees your answers.
            </p>
          </CardHeader>
          <CardContent>
            <PatientForm onSubmit={submit} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function HistoryTab({ version }: { version: number }) {
  const { data, error, reload } = useApi<PredictionHistoryItem[]>(`/ml/predictions?limit=100&v=${version}`)
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return <LoadingGrid cards={2} />
  if (!data.length)
    return <EmptyState icon={ClipboardList} title="No health checks yet" body="When you do a health check, it is saved here so you can look back at it." />
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <THead>
            <TR>
              <TH>When</TH>
              <TH>Result</TH>
              <TH>Group</TH>
            </TR>
          </THead>
          <TBody>
            {data.map((p) => (
              <TR key={p.id}>
                <TD>{dateTime(p.created_at)}</TD>
                <TD className="font-medium">about {Math.round(p.probability * 100)} in 100</TD>
                <TD>
                  <Badge variant={BAND_META[p.risk_band].variant}>{BAND_META[p.risk_band].label}</Badge>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export default function HealthCheck() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'history' ? 'history' : 'check'
  const [version, setVersion] = useState(0)
  return (
    <>
      <PageHeader
        title="Health Check"
        description="See how your answers compare with thousands of other people, and whether it might be worth getting a blood sugar test."
      />
      <Alert variant="warning" className="mb-5">
        <ShieldAlert />
        <span className="text-sm">
          This is <strong>not a diagnosis</strong>. Only a blood test from a doctor or pharmacist can show whether someone has diabetes.
        </span>
      </Alert>
      <Tabs value={tab} onValueChange={(v) => setParams(v === 'history' ? { tab: v } : {}, { replace: true })}>
        <TabsList>
          <TabsTrigger value="check">
            <HeartPulse className="mr-1.5 size-4" /> New check
          </TabsTrigger>
          <TabsTrigger value="history">
            <History className="mr-1.5 size-4" /> My past checks
          </TabsTrigger>
        </TabsList>
        <TabsContent value="check">
          <CheckTab onSaved={() => setVersion((v) => v + 1)} />
        </TabsContent>
        <TabsContent value="history">
          <HistoryTab version={version} />
        </TabsContent>
      </Tabs>
      <p className="mt-6 flex items-center gap-1 text-xs text-muted-foreground">
        Curious how accurate this is?{' '}
        <Link to="/learn/accuracy" className="inline-flex items-center gap-0.5 font-medium text-primary hover:underline">
          See how well it works <ArrowRight className="size-3" />
        </Link>
      </p>
    </>
  )
}
