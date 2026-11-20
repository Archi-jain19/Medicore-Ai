import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertCircle, CheckCircle2 } from 'lucide-react'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { FormField, Spinner } from '@/components/ui/misc'
import { api, errorMessage } from '@/services/api'
import { forgotSchema, resetSchema, type ForgotValues, type ResetValues } from '@/utils/validation'
import { AuthShell } from './AuthShell'

const backToLogin = (
  <Link to="/login" className="font-medium text-primary hover:underline">
    Back to sign in
  </Link>
)

export function ForgotPassword() {
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotValues>({ resolver: zodResolver(forgotSchema) })

  const onSubmit = async (v: ForgotValues) => {
    setError(null)
    try {
      const { data } = await api.post<{ message: string }>('/auth/forgot-password', v)
      setMessage(data.message)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <AuthShell title="Reset your password" description="Enter your email and we will send you a link to choose a new password. The link works for 15 minutes." footer={backToLogin}>
      {message ? (
        <Alert variant="info">
          <CheckCircle2 />
          <span>{message}</span>
        </Alert>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="grid gap-4" noValidate>
          {error && (
            <Alert variant="destructive">
              <AlertCircle />
              <span>{error}</span>
            </Alert>
          )}
          <FormField id="email" label="Email" error={errors.email?.message}>
            <Input id="email" type="email" autoComplete="email" aria-invalid={!!errors.email} {...register('email')} />
          </FormField>
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting && <Spinner />} Send reset link
          </Button>
        </form>
      )}
    </AuthShell>
  )
}

export function ResetPassword() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const [done, setDone] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetValues>({ resolver: zodResolver(resetSchema) })

  const onSubmit = async (v: ResetValues) => {
    setError(null)
    try {
      const { data } = await api.post<{ message: string }>('/auth/reset-password', { token, new_password: v.new_password })
      setDone(data.message)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <AuthShell title="Choose a new password" description="Pick a new password. Your reset link can only be used once." footer={backToLogin}>
      {!token ? (
        <Alert variant="destructive">
          <AlertCircle />
          <span>
            This reset link is missing its token. <Link to="/forgot-password" className="underline">Request a new link</Link>.
          </span>
        </Alert>
      ) : done ? (
        <Alert variant="info">
          <CheckCircle2 />
          <span>{done}</span>
        </Alert>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="grid gap-4" noValidate>
          {error && (
            <Alert variant="destructive">
              <AlertCircle />
              <span>{error}</span>
            </Alert>
          )}
          <FormField id="new_password" label="New password" error={errors.new_password?.message}>
            <Input id="new_password" type="password" autoComplete="new-password" {...register('new_password')} />
          </FormField>
          <FormField id="confirm" label="Confirm password" error={errors.confirm?.message}>
            <Input id="confirm" type="password" autoComplete="new-password" {...register('confirm')} />
          </FormField>
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting && <Spinner />} Update password
          </Button>
        </form>
      )}
    </AuthShell>
  )
}
