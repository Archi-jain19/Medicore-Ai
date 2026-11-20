import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { FormField, Spinner } from '@/components/ui/misc'
import { useAuth } from '@/hooks/useAuth'
import { errorMessage } from '@/services/api'
import { registerSchema, type RegisterValues } from '@/utils/validation'
import { AuthShell } from './AuthShell'

export default function Register() {
  const { register: signUp, user } = useAuth()
  const navigate = useNavigate()
  const [serverError, setServerError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) })

  if (user) return <Navigate to="/dashboard" replace />

  const onSubmit = async (v: RegisterValues) => {
    setServerError(null)
    try {
      await signUp(v.email, v.password, v.full_name?.trim())
      navigate('/dashboard', { replace: true })
    } catch (e) {
      setServerError(errorMessage(e))
    }
  }

  return (
    <AuthShell
      title="Create your account"
      description="It is free and takes about a minute."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-primary hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} className="grid gap-4" noValidate>
        {serverError && (
          <Alert variant="destructive">
            <AlertCircle />
            <span>{serverError}</span>
          </Alert>
        )}
        <FormField id="full_name" label="Your name (optional)" error={errors.full_name?.message}>
          <Input id="full_name" autoComplete="name" {...register('full_name')} />
        </FormField>
        <FormField id="email" label="Email" error={errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" aria-invalid={!!errors.email} {...register('email')} />
        </FormField>
        <FormField id="password" label="Password" error={errors.password?.message} hint="At least 8 characters, with a letter and a number">
          <Input id="password" type="password" autoComplete="new-password" aria-invalid={!!errors.password} {...register('password')} />
        </FormField>
        <FormField id="confirm" label="Confirm password" error={errors.confirm?.message}>
          <Input id="confirm" type="password" autoComplete="new-password" aria-invalid={!!errors.confirm} {...register('confirm')} />
        </FormField>
        <label className="flex items-start gap-2 text-sm text-muted-foreground">
          <input type="checkbox" className="mt-1 accent-[var(--primary)]" {...register('accept')} />
          <span>
            I understand MediCore is not a doctor and cannot diagnose me or tell me which medicine to take. I agree to the{' '}
            <Link to="/terms" target="_blank" className="text-primary underline">
              Terms of use
            </Link>{' '}
            and the{' '}
            <Link to="/privacy" target="_blank" className="text-primary underline">
              Privacy policy
            </Link>
            .
          </span>
        </label>
        {errors.accept && <p className="-mt-2 text-xs text-destructive">{errors.accept.message}</p>}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Spinner />} Create account
        </Button>
      </form>
    </AuthShell>
  )
}
