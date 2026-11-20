import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { AlertCircle, CheckCircle2, Download, LogOut, Trash2 } from 'lucide-react'
import { ErrorState, PageHeader } from '@/components/common'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/input'
import { FormField, Skeleton, Spinner } from '@/components/ui/misc'
import { useApi } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { api, errorMessage } from '@/services/api'
import type { Profile } from '@/types/api'
import { dateTime } from '@/utils/format'
import { passwordSchema } from '@/utils/validation'

type Msg = { kind: 'ok' | 'err'; text: string } | null

function Feedback({ msg }: { msg: Msg }) {
  if (!msg) return null
  return (
    <Alert variant={msg.kind === 'ok' ? 'info' : 'destructive'}>
      {msg.kind === 'ok' ? <CheckCircle2 /> : <AlertCircle />}
      <span>{msg.text}</span>
    </Alert>
  )
}

const profileSchema = z.object({
  full_name: z.string().max(120).optional(),
  notify_reminders: z.boolean(),
  data_retention_days: z.string(),
})
type ProfileValues = z.infer<typeof profileSchema>

function ProfileCard({ profile, onSaved }: { profile: Profile; onSaved: () => void }) {
  const { refresh } = useAuth()
  const [msg, setMsg] = useState<Msg>(null)
  const { register, handleSubmit, formState: { isSubmitting, isDirty } } = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      full_name: profile.full_name ?? '',
      notify_reminders: profile.notify_reminders,
      data_retention_days: profile.data_retention_days ? String(profile.data_retention_days) : '',
    },
  })
  const save = async (v: ProfileValues) => {
    setMsg(null)
    const days = v.data_retention_days ? Number(v.data_retention_days) : null
    if (days && (!profile.data_retention_days || days < profile.data_retention_days)) {
      if (!window.confirm(`Anything older than ${days} days (your questions, lab results, health checks and activity) will be deleted now, and again from then on. Continue?`)) return
    }
    try {
      await api.put('/users/me/profile', { full_name: v.full_name?.trim() || null, notify_reminders: v.notify_reminders, data_retention_days: days })
      setMsg({ kind: 'ok', text: 'Settings saved.' })
      await refresh()
      onSaved()
    } catch (e) {
      setMsg({ kind: 'err', text: errorMessage(e) })
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>About you</CardTitle>
        <CardDescription>
          Signed in as {profile.email}. Joined {dateTime(profile.created_at)}.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(save)} className="grid gap-4">
          <Feedback msg={msg} />
          <FormField id="full_name" label="Your name">
            <Input id="full_name" autoComplete="name" {...register('full_name')} />
          </FormField>
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" className="mt-1 accent-[var(--primary)]" {...register('notify_reminders')} />
            <span>
              <span className="font-medium">Medicine reminder alerts</span>
              <span className="block text-muted-foreground">Shows a pop-up when a medicine is due, while MediCore is open in your browser. We do not send emails or text messages for reminders yet.</span>
            </span>
          </label>
          <FormField id="data_retention_days" label="Delete my old history automatically" hint="This covers your questions, lab results, health checks and activity. Your medicine reminders are kept until you delete them.">
            <Select id="data_retention_days" {...register('data_retention_days')}>
              <option value="">Never (I will delete it myself)</option>
              <option value="30">After 30 days</option>
              <option value="90">After 90 days</option>
              <option value="180">After 6 months</option>
              <option value="365">After 1 year</option>
            </Select>
          </FormField>
          <div>
            <Button type="submit" disabled={isSubmitting || !isDirty}>
              {isSubmitting && <Spinner />} Save
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

const pwSchema = z
  .object({ current_password: z.string().min(1, 'Required'), new_password: passwordSchema, confirm: z.string() })
  .refine((v) => v.new_password === v.confirm, { path: ['confirm'], message: 'Passwords do not match' })
type PwValues = z.infer<typeof pwSchema>

function PasswordCard() {
  const { setToken } = useAuth()
  const [msg, setMsg] = useState<Msg>(null)
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<PwValues>({ resolver: zodResolver(pwSchema) })
  const save = async (v: PwValues) => {
    setMsg(null)
    try {
      const { data } = await api.post<{ access_token: string }>('/auth/change-password', {
        current_password: v.current_password,
        new_password: v.new_password,
      })
      setToken(data.access_token) // other devices are signed out; this one keeps a fresh session
      reset()
      setMsg({ kind: 'ok', text: 'Password changed. Other signed-in devices have been signed out.' })
    } catch (e) {
      setMsg({ kind: 'err', text: errorMessage(e) })
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Change my password</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(save)} className="grid gap-4" noValidate>
          <Feedback msg={msg} />
          <FormField id="current_password" label="Current password" error={errors.current_password?.message}>
            <Input id="current_password" type="password" autoComplete="current-password" {...register('current_password')} />
          </FormField>
          <FormField id="new_password" label="New password" error={errors.new_password?.message} hint="8+ characters with a letter and a number">
            <Input id="new_password" type="password" autoComplete="new-password" {...register('new_password')} />
          </FormField>
          <FormField id="confirm_pw" label="Confirm new password" error={errors.confirm?.message}>
            <Input id="confirm_pw" type="password" autoComplete="new-password" {...register('confirm')} />
          </FormField>
          <div>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting && <Spinner />} Update password
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

const SCOPES = [
  { scope: 'conversations', label: 'My questions and answers' },
  { scope: 'reports', label: 'My lab results' },
  { scope: 'predictions', label: 'My health checks' },
  { scope: 'reminders', label: 'My medicine reminders' },
  { scope: 'activity', label: 'My activity list' },
] as const

function PrivacyCard() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [msg, setMsg] = useState<Msg>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [pw, setPw] = useState('')
  const [confirmText, setConfirmText] = useState('')

  const exportData = async () => {
    setBusy('export')
    setMsg(null)
    try {
      const { data } = await api.get<Blob>('/users/me/export', { responseType: 'blob' })
      const url = URL.createObjectURL(data)
      const a = document.createElement('a')
      a.href = url
      a.download = 'medicore-data-export.json'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setMsg({ kind: 'err', text: errorMessage(e) })
    } finally {
      setBusy(null)
    }
  }
  const purge = async (scope: string, label: string) => {
    if (!window.confirm(`Delete all of this? "${label}". It cannot be undone.`)) return
    setBusy(scope)
    setMsg(null)
    try {
      const { data } = await api.post<{ deleted: number }>('/users/me/purge', { scope })
      setMsg({ kind: 'ok', text: `Done. We deleted ${data.deleted} ${data.deleted === 1 ? 'item' : 'items'} from "${label}".` })
    } catch (e) {
      setMsg({ kind: 'err', text: errorMessage(e) })
    } finally {
      setBusy(null)
    }
  }
  const deleteAccount = async () => {
    setBusy('account')
    setMsg(null)
    try {
      await api.delete('/users/me', { data: { password: pw, confirm: confirmText } })
      logout()
      navigate('/', { replace: true })
    } catch (e) {
      setMsg({ kind: 'err', text: errorMessage(e) })
      setBusy(null)
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Your data</CardTitle>
        <CardDescription>We do not keep the lab report files you upload, and only you can see your information.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <Feedback msg={msg} />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-medium">Get a copy of my data</p>
            <p className="text-sm text-muted-foreground">Download everything we have saved about you, as a file you can keep.</p>
          </div>
          <Button variant="outline" onClick={exportData} disabled={!!busy}>
            {busy === 'export' ? <Spinner /> : <Download />} Download
          </Button>
        </div>
        <div className="space-y-2">
          <p className="font-medium">Delete some of my data</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {SCOPES.map(({ scope, label }) => (
              <Button key={scope} variant="outline" className="justify-between" disabled={!!busy} onClick={() => purge(scope, label)}>
                {label} {busy === scope ? <Spinner /> : <Trash2 />}
              </Button>
            ))}
          </div>
        </div>
        <div className="space-y-3 rounded-lg border border-destructive/30 p-4">
          <p className="font-medium text-destructive">Delete my account</p>
          <p className="text-sm text-muted-foreground">This permanently removes your account and everything saved in it. It cannot be undone.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField id="del_pw" label="Password">
              <Input id="del_pw" type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} />
            </FormField>
            <FormField id="del_confirm" label='Type "DELETE" to confirm'>
              <Input id="del_confirm" value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
            </FormField>
          </div>
          <Button variant="destructive" disabled={!pw || confirmText !== 'DELETE' || !!busy} onClick={deleteAccount}>
            {busy === 'account' ? <Spinner /> : <Trash2 />} Delete my account
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export default function Settings() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [tick, setTick] = useState(0)
  const profile = useApi<Profile>(`/users/me/profile?t=${tick}`)
  return (
    <>
      <PageHeader
        title="Settings & Privacy"
        actions={
          <Button
            variant="outline"
            onClick={() => {
              logout()
              navigate('/login')
            }}
          >
            <LogOut /> Sign out
          </Button>
        }
      />
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-4">
          {profile.error ? (
            <ErrorState message={profile.error} onRetry={profile.reload} />
          ) : !profile.data ? (
            <Skeleton className="h-72 rounded-xl" />
          ) : (
            <ProfileCard key={tick} profile={profile.data} onSaved={() => setTick((t) => t + 1)} />
          )}
          <PasswordCard />
        </div>
        <PrivacyCard />
      </div>
    </>
  )
}
