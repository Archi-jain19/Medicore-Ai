import { useEffect, useState } from 'react'
import { useFieldArray, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { AlertCircle, BellRing, Check, Info, Pause, Pencil, Play, Plus, SkipForward, Trash2, X } from 'lucide-react'
import { EmptyState, ErrorState, PageHeader } from '@/components/common'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/input'
import { FormField, Skeleton, Spinner, Table, TBody, TD, TH, THead, TR } from '@/components/ui/misc'
import { useApi } from '@/hooks/useApi'
import { cn } from '@/lib/utils'
import { api, errorMessage } from '@/services/api'
import type { Dose, DoseEvent, Frequency, Reminder } from '@/types/api'
import { friendlyDate, friendlyTime, localDate, localTime } from '@/utils/dates'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const FREQ_LABEL: Record<Frequency, string> = {
  daily: 'Every day',
  every_other_day: 'Every other day',
  weekly: 'On certain days of the week',
  as_needed: 'Only when I need it (no reminders)',
}

const schema = z
  .object({
    medication_name: z.string().trim().min(1, 'Please enter the name of the medicine').max(120),
    dosage_note: z.string().max(200).optional(),
    frequency: z.enum(['daily', 'every_other_day', 'weekly', 'as_needed']),
    times: z.array(z.object({ value: z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'Please enter a time') })).max(8),
    days_of_week: z.array(z.number()),
    start_date: z.string().min(1, 'Start date is required'),
    end_date: z.string().optional(),
  })
  .superRefine((v, ctx) => {
    if (v.frequency !== 'as_needed' && v.times.length === 0) ctx.addIssue({ code: 'custom', path: ['times'], message: 'Please add at least one time' })
    if (new Set(v.times.map((t) => t.value)).size !== v.times.length) ctx.addIssue({ code: 'custom', path: ['times'], message: 'Each time must be different' })
    if (v.frequency === 'weekly' && v.days_of_week.length === 0) ctx.addIssue({ code: 'custom', path: ['days_of_week'], message: 'Please choose at least one day' })
    if (v.end_date && v.end_date < v.start_date) ctx.addIssue({ code: 'custom', path: ['end_date'], message: 'The end date must be after the start date' })
  })
type FormValues = z.infer<typeof schema>

function toPayload(v: FormValues, isActive = true) {
  return {
    medication_name: v.medication_name,
    dosage_note: v.dosage_note?.trim() || null,
    frequency: v.frequency,
    times: v.frequency === 'as_needed' ? [] : v.times.map((t) => t.value),
    days_of_week: v.frequency === 'weekly' ? v.days_of_week : null,
    start_date: v.start_date,
    end_date: v.end_date || null,
    is_active: isActive,
  }
}

function ReminderForm({ initial, onSaved, onCancel }: { initial?: Reminder; onSaved: () => void; onCancel?: () => void }) {
  const [serverError, setServerError] = useState<string | null>(null)
  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: initial
      ? {
          medication_name: initial.medication_name,
          dosage_note: initial.dosage_note ?? '',
          frequency: initial.frequency,
          times: initial.times.map((value) => ({ value })),
          days_of_week: initial.days_of_week ?? [],
          start_date: initial.start_date,
          end_date: initial.end_date ?? '',
        }
      : { medication_name: '', dosage_note: '', frequency: 'daily', times: [{ value: '08:00' }], days_of_week: [], start_date: localDate(), end_date: '' },
  })
  const times = useFieldArray({ control, name: 'times' })
  const freq = watch('frequency')
  const days = watch('days_of_week')

  const submit = async (v: FormValues) => {
    setServerError(null)
    try {
      if (initial) await api.put(`/reminders/${initial.id}`, toPayload(v, initial.is_active))
      else await api.post('/reminders', toPayload(v))
      if (!initial) reset()
      onSaved()
    } catch (e) {
      setServerError(errorMessage(e))
    }
  }

  return (
    <form onSubmit={handleSubmit(submit)} className="grid gap-4" noValidate>
      {serverError && (
        <Alert variant="destructive">
          <AlertCircle />
          <span>{serverError}</span>
        </Alert>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="medication_name" label="Medicine name" error={errors.medication_name?.message}>
          <Input id="medication_name" aria-invalid={!!errors.medication_name} {...register('medication_name')} />
        </FormField>
        <FormField id="dosage_note" label="Dose or instructions (optional)" hint="Copy this from your medicine label or prescription." error={errors.dosage_note?.message}>
          <Input id="dosage_note" placeholder="e.g. 1 tablet after food" {...register('dosage_note')} />
        </FormField>
        <div className="sm:col-span-2">
          <FormField id="frequency" label="How often do you take it?">
            <Select id="frequency" {...register('frequency')}>
              {Object.entries(FREQ_LABEL).map(([k, l]) => (
                <option key={k} value={k}>
                  {l}
                </option>
              ))}
            </Select>
          </FormField>
        </div>
        <FormField id="start_date" label="Start date" error={errors.start_date?.message}>
          <Input id="start_date" type="date" {...register('start_date')} />
        </FormField>
        <FormField id="end_date" label="End date (optional)" hint="Leave empty if there is no end date." error={errors.end_date?.message}>
          <Input id="end_date" type="date" {...register('end_date')} />
        </FormField>
      </div>
      {freq === 'weekly' && (
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Which days?</legend>
          <div className="flex flex-wrap gap-2">
            {DAYS.map((d, i) => {
              const on = days.includes(i)
              return (
                <button
                  key={d}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setValue('days_of_week', on ? days.filter((x) => x !== i) : [...days, i].sort(), { shouldValidate: true })}
                  className={cn('rounded-md border px-3 py-1.5 text-sm', on ? 'border-primary bg-primary text-primary-foreground' : 'bg-card hover:bg-secondary')}
                >
                  {d}
                </button>
              )
            })}
          </div>
          {errors.days_of_week && <p className="text-xs text-destructive">{errors.days_of_week.message}</p>}
        </fieldset>
      )}
      {freq !== 'as_needed' && (
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">What time do you take it?</legend>
          <div className="flex flex-wrap items-center gap-2">
            {times.fields.map((f, i) => (
              <div key={f.id} className="flex items-center gap-1">
                <Input type="time" aria-label={`Time ${i + 1}`} className="w-32" {...register(`times.${i}.value` as const)} />
                <Button type="button" variant="ghost" size="icon" aria-label={`Remove time ${i + 1}`} onClick={() => times.remove(i)}>
                  <X />
                </Button>
              </div>
            ))}
            {times.fields.length < 8 && (
              <Button type="button" variant="outline" size="sm" onClick={() => times.append({ value: '12:00' })}>
                <Plus /> Add time
              </Button>
            )}
          </div>
          {(errors.times?.message || errors.times?.root?.message) && (
            <p className="text-xs text-destructive">{errors.times?.message || errors.times?.root?.message}</p>
          )}
        </fieldset>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Spinner />} {initial ? 'Save changes' : 'Add reminder'}
        </Button>
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  )
}

function useDueNotifications(doses: Dose[] | null, enabled: boolean) {
  useEffect(() => {
    if (!enabled || !doses?.length || !('Notification' in window) || Notification.permission !== 'granted') return
    const notified = new Set<string>()
    const tick = () => {
      const now = localTime()
      for (const d of doses) {
        const key = `${d.reminder_id}-${d.scheduled_time}`
        if (d.status === 'pending' && d.scheduled_time === now && !notified.has(key)) {
          notified.add(key)
          new Notification(`Time for ${d.medication_name}`, { body: d.dosage_note ?? 'Medication reminder from MediCore AI' })
        }
      }
    }
    tick()
    const id = window.setInterval(tick, 30_000)
    return () => window.clearInterval(id)
  }, [doses, enabled])
}

export default function Reminders() {
  const today = localDate()
  const [tick, setTick] = useState(0)
  const list = useApi<Reminder[]>(`/reminders?today=${today}&t=${tick}`)
  const schedule = useApi<Dose[]>(`/reminders/schedule?day=${today}&t=${tick}`)
  const history = useApi<DoseEvent[]>(`/reminders/history?days=30&t=${tick}`)
  const profile = useApi<{ notify_reminders: boolean }>('/users/me/profile')
  const [editing, setEditing] = useState<Reminder | null>(null)
  const [actionErr, setActionErr] = useState<string | null>(null)
  const [perm, setPerm] = useState<NotificationPermission | 'unsupported'>('Notification' in window ? Notification.permission : 'unsupported')
  const refresh = () => setTick((t) => t + 1)
  useDueNotifications(schedule.data, !!profile.data?.notify_reminders)

  const act = async (fn: () => Promise<unknown>) => {
    setActionErr(null)
    try {
      await fn()
      refresh()
    } catch (e) {
      setActionErr(errorMessage(e))
    }
  }
  const logDose = (d: Dose, status: 'taken' | 'skipped') =>
    act(() => api.post(`/reminders/${d.reminder_id}/events`, { scheduled_date: d.scheduled_date, scheduled_time: d.scheduled_time, status }))
  const logAsNeeded = (r: Reminder) =>
    act(() => api.post(`/reminders/${r.id}/events`, { scheduled_date: today, scheduled_time: localTime(), status: 'taken' }))
  const toggle = (r: Reminder) =>
    act(() =>
      api.put(`/reminders/${r.id}`, {
        medication_name: r.medication_name, dosage_note: r.dosage_note, frequency: r.frequency, times: r.times,
        days_of_week: r.days_of_week, start_date: r.start_date, end_date: r.end_date, is_active: !r.is_active,
      }),
    )
  const remove = (r: Reminder) => {
    if (window.confirm(`Delete ${r.medication_name} and everything you marked for it? This cannot be undone.`)) void act(() => api.delete(`/reminders/${r.id}`))
  }
  const nowHM = localTime()

  return (
    <>
      <PageHeader title="Medicine Reminders" description="Keep track of your medicines, and mark each dose as you take it." />
      <Alert variant="info" className="mb-4">
        <Info />
        <span className="text-sm">
          We only remind you. We never suggest, check or change your medicines or doses. Follow your doctor's instructions, and ask your
          doctor or pharmacist before you make any change.
        </span>
      </Alert>
      {actionErr && (
        <Alert variant="destructive" className="mb-4">
          <AlertCircle />
          <span>{actionErr}</span>
        </Alert>
      )}

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle>Today · {new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}</CardTitle>
              {profile.data?.notify_reminders && perm === 'default' && (
                <Button size="sm" variant="outline" onClick={() => void Notification.requestPermission().then(setPerm)}>
                  <BellRing /> Turn on alerts
                </Button>
              )}
            </div>
            {profile.data?.notify_reminders && perm === 'granted' && (
              <p className="text-xs text-muted-foreground">Alerts are on. You will see a pop-up when a dose is due, while MediCore is open in your browser.</p>
            )}
          </CardHeader>
          <CardContent>
            {schedule.error ? (
              <ErrorState message={schedule.error} onRetry={schedule.reload} />
            ) : !schedule.data ? (
              <Skeleton className="h-24" />
            ) : schedule.data.length === 0 ? (
              <EmptyState icon={BellRing} title="No medicines to take today" body="Your medicines will show up here on the days you take them." />
            ) : (
              <ul className="divide-y">
                {schedule.data.map((d) => {
                  const missed = d.status === 'pending' && d.scheduled_time < nowHM
                  return (
                    <li key={`${d.reminder_id}-${d.scheduled_time}`} className="flex flex-wrap items-center justify-between gap-2 py-3">
                      <div>
                        <p className="font-medium">
                          <span className="mr-2 tabular-nums text-muted-foreground">{friendlyTime(d.scheduled_time)}</span>
                          {d.medication_name}
                        </p>
                        {d.dosage_note && <p className="text-xs text-muted-foreground">{d.dosage_note}</p>}
                      </div>
                      <div className="flex items-center gap-2">
                        {d.status !== 'pending' ? (
                          <Badge variant={d.status === 'taken' ? 'success' : 'outline'}>{d.status}</Badge>
                        ) : missed ? (
                          <Badge variant="warning">overdue</Badge>
                        ) : null}
                        <Button size="sm" variant={d.status === 'taken' ? 'secondary' : 'teal'} onClick={() => logDose(d, 'taken')}>
                          <Check /> Taken
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => logDose(d, 'skipped')}>
                          <SkipForward /> Skip
                        </Button>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{editing ? `Edit ${editing.medication_name}` : 'Add a medicine'}</CardTitle>
          </CardHeader>
          <CardContent>
            <ReminderForm
              key={editing?.id ?? 'new'}
              initial={editing ?? undefined}
              onSaved={() => {
                setEditing(null)
                refresh()
              }}
              onCancel={editing ? () => setEditing(null) : undefined}
            />
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Your medicines</CardTitle>
        </CardHeader>
        <CardContent>
          {list.error ? (
            <ErrorState message={list.error} onRetry={list.reload} />
          ) : !list.data ? (
            <Skeleton className="h-20" />
          ) : list.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">You have not added any medicines yet.</p>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Medicine</TH>
                  <TH>When</TH>
                  <TH>Dates</TH>
                  <TH>Status</TH>
                  <TH className="text-right">Actions</TH>
                </TR>
              </THead>
              <TBody>
                {list.data.map((r) => (
                  <TR key={r.id}>
                    <TD>
                      <p className="font-medium">{r.medication_name}</p>
                      {r.dosage_note && <p className="text-xs text-muted-foreground">{r.dosage_note}</p>}
                    </TD>
                    <TD className="text-sm">
                      {FREQ_LABEL[r.frequency]}
                      {r.frequency === 'weekly' && r.days_of_week && <span className="block text-xs text-muted-foreground">{r.days_of_week.map((d) => DAYS[d]).join(', ')}</span>}
                      {r.times.length > 0 && <span className="block text-xs tabular-nums text-muted-foreground">{r.times.map(friendlyTime).join(' · ')}</span>}
                    </TD>
                    <TD className="text-xs text-muted-foreground">
                      From {friendlyDate(r.start_date)}
                      {r.end_date ? ` to ${friendlyDate(r.end_date)}` : ', no end date'}
                    </TD>
                    <TD>
                      <Badge variant={r.status === 'active' ? 'success' : r.status === 'paused' ? 'warning' : 'outline'}>
                        {{ active: 'Active', paused: 'Paused', ended: 'Finished', scheduled: 'Starts later' }[r.status]}
                      </Badge>
                    </TD>
                    <TD>
                      <div className="flex justify-end gap-1">
                        {r.frequency === 'as_needed' && r.is_active && (
                          <Button size="sm" variant="outline" onClick={() => logAsNeeded(r)}>
                            <Check /> I took a dose now
                          </Button>
                        )}
                        <Button size="icon" variant="ghost" aria-label={r.is_active ? `Pause ${r.medication_name}` : `Resume ${r.medication_name}`} onClick={() => toggle(r)}>
                          {r.is_active ? <Pause /> : <Play />}
                        </Button>
                        <Button size="icon" variant="ghost" aria-label={`Edit ${r.medication_name}`} onClick={() => setEditing(r)}>
                          <Pencil />
                        </Button>
                        <Button size="icon" variant="ghost" aria-label={`Delete ${r.medication_name}`} onClick={() => remove(r)}>
                          <Trash2 />
                        </Button>
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>What you took (last 30 days)</CardTitle>
        </CardHeader>
        <CardContent>
          {history.error ? (
            <ErrorState message={history.error} onRetry={history.reload} />
          ) : !history.data ? (
            <Skeleton className="h-20" />
          ) : history.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing marked yet. When you tap Taken, it appears here.</p>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Date</TH>
                  <TH>Time</TH>
                  <TH>Medicine</TH>
                  <TH>Status</TH>
                </TR>
              </THead>
              <TBody>
                {history.data.map((e) => (
                  <TR key={e.id}>
                    <TD>{friendlyDate(e.scheduled_date)}</TD>
                    <TD className="tabular-nums">{friendlyTime(e.scheduled_time)}</TD>
                    <TD>{e.medication_name}</TD>
                    <TD>
                      <Badge variant={e.status === 'taken' ? 'success' : 'outline'}>{e.status}</Badge>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  )
}
