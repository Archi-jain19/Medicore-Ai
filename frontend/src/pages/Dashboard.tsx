import { Link } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowRight, BellRing, Check, FileText, HeartPulse, MapPin, MessageSquareText, type LucideIcon } from 'lucide-react'
import { EmptyState, ErrorState, PageHeader } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { useApi } from '@/hooks/useApi'
import { cn } from '@/lib/utils'
import type { DashboardSummary, Dose } from '@/types/api'
import { friendlyTime, localDate } from '@/utils/dates'
import { dateTime, shortDate } from '@/utils/format'

const TASKS: { to: string; icon: LucideIcon; title: string; body: string; tone: string }[] = [
  { to: '/assistant', icon: MessageSquareText, title: 'Ask a health question', body: 'Get a clear answer in plain words, with the sources it came from.', tone: 'bg-accent text-accent-foreground' },
  { to: '/reports', icon: FileText, title: 'Understand my lab results', body: 'Upload your lab report and see what each test means.', tone: 'bg-sky/15 text-[oklch(0.45_0.12_235)]' },
  { to: '/analytics', icon: HeartPulse, title: 'Do a 2-minute health check', body: 'Answer a few questions to see how you compare with others.', tone: 'bg-destructive/10 text-destructive' },
  { to: '/locator', icon: MapPin, title: 'Find care near me', body: 'Hospitals, clinics and pharmacies close to you.', tone: 'bg-success/15 text-success' },
  { to: '/reminders', icon: BellRing, title: 'Medicine reminders', body: 'Keep track of your medicines so you never miss a dose.', tone: 'bg-warning/25 text-[oklch(0.45_0.1_70)]' },
]

const axis = { fontSize: 11, fill: 'var(--muted-foreground)' }

export default function Dashboard() {
  const today = localDate()
  const summary = useApi<DashboardSummary>('/dashboard/summary')
  const doses = useApi<Dose[]>(`/reminders/schedule?day=${today}`)
  const s = summary.data
  const name = s?.user.full_name?.split(' ')[0]
  const pending = doses.data?.filter((d) => d.status === 'pending') ?? []
  const checks = s?.my_prediction_trend ?? []

  return (
    <>
      <PageHeader title={name ? `Hello, ${name}` : 'Hello'} description="What would you like to do today?" />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {TASKS.map(({ to, icon: Icon, title, body, tone }) => (
          <Link key={to} to={to} className="group focus-visible:outline-none">
            <Card className="h-full transition-shadow group-hover:shadow-md group-focus-visible:ring-[3px] group-focus-visible:ring-ring/50">
              <CardContent className="flex h-full flex-col gap-3 p-5">
                <span className={cn('grid size-11 place-items-center rounded-xl', tone)}>
                  <Icon className="size-5" />
                </span>
                <div className="space-y-1">
                  <h2 className="font-semibold text-primary">{title}</h2>
                  <p className="text-sm text-muted-foreground">{body}</p>
                </div>
                <span className="mt-auto flex items-center gap-1 pt-1 text-sm font-medium text-primary">
                  Open <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
                </span>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Medicines today</CardTitle>
          </CardHeader>
          <CardContent>
            {doses.error ? (
              <ErrorState message={doses.error} onRetry={doses.reload} />
            ) : !doses.data ? (
              <Skeleton className="h-20" />
            ) : doses.data.length === 0 ? (
              <EmptyState
                icon={BellRing}
                title="No medicines to take today"
                body="Add your medicines and we will list them here on the days you take them."
                action={
                  <Link to="/reminders" className="text-sm font-medium text-primary hover:underline">
                    Add a medicine reminder
                  </Link>
                }
              />
            ) : (
              <>
                <ul className="divide-y">
                  {doses.data.map((d) => (
                    <li key={`${d.reminder_id}-${d.scheduled_time}`} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                      <span>
                        <span className="mr-2 tabular-nums text-muted-foreground">{friendlyTime(d.scheduled_time)}</span>
                        <span className="font-medium">{d.medication_name}</span>
                      </span>
                      {d.status === 'taken' ? (
                        <Badge variant="success">
                          <Check className="size-3" /> Taken
                        </Badge>
                      ) : d.status === 'skipped' ? (
                        <Badge variant="outline">Skipped</Badge>
                      ) : (
                        <Badge variant="warning">To take</Badge>
                      )}
                    </li>
                  ))}
                </ul>
                <Link to="/reminders" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
                  {pending.length > 0 ? 'Mark as taken' : 'Manage reminders'} <ArrowRight className="size-3.5" />
                </Link>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Your recent activity</CardTitle>
          </CardHeader>
          <CardContent>
            {summary.error ? (
              <ErrorState message={summary.error} onRetry={summary.reload} />
            ) : !s ? (
              <Skeleton className="h-20" />
            ) : s.recent_activity.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing yet. Pick something above to get started.</p>
            ) : (
              <ul className="divide-y">
                {s.recent_activity.slice(0, 6).map((ev) => (
                  <li key={ev.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                    <span>{ev.label}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">{dateTime(ev.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {checks.length > 1 && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle>Your health check results over time</CardTitle>
            <p className="text-sm text-muted-foreground">
              Each point is one health check. Higher means your answers were more like people who have diabetes or prediabetes. It is not a
              diagnosis.
            </p>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={checks.map((p) => ({ ...p, label: shortDate(p.created_at), chance: Math.round(p.probability * 100) }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="label" tick={axis} />
                <YAxis tick={axis} domain={[0, 100]} unit="" label={{ value: 'Chance (in 100)', angle: -90, position: 'insideLeft', fontSize: 11 }} />
                <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid var(--border)', fontSize: 12 }} formatter={(v: number) => [`about ${v} in 100`, 'Chance']} />
                <Line type="monotone" dataKey="chance" stroke="var(--chart-1)" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      <p className="mt-6 text-center text-xs text-muted-foreground">
        Want to know how this works, or how accurate it is?{' '}
        <Link to="/learn" className="font-medium text-primary hover:underline">
          Read how it works
        </Link>
      </p>
    </>
  )
}
