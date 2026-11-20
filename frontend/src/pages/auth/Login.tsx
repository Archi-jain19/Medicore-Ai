import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { FormField, Spinner } from '@/components/ui/misc'
import { useAuth } from '@/hooks/useAuth'
import { errorMessage } from '@/services/api'
import { loginSchema, type LoginValues } from '@/utils/validation'
import { AuthShell } from './AuthShell'

export default function Login() {
  const { login, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/dashboard'
  const [serverError, setServerError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) })

  if (user) return <Navigate to={from} replace />

  const onSubmit = async (v: LoginValues) => {
    setServerError(null)
    try {
      await login(v.email, v.password)
      navigate(from, { replace: true })
    } catch (e) {
      setServerError(errorMessage(e))
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      description="Sign in to see your health information."
      footer={
        <>
          New here?{' '}
          <Link to="/register" className="font-medium text-primary hover:underline">
            Create an account
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
        <FormField id="email" label="Email" error={errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" aria-invalid={!!errors.email} {...register('email')} />
        </FormField>
        <FormField id="password" label="Password" error={errors.password?.message}>
          <Input id="password" type="password" autoComplete="current-password" aria-invalid={!!errors.password} {...register('password')} />
        </FormField>
        <div className="flex justify-end">
          <Link to="/forgot-password" className="text-sm text-primary hover:underline">
            Forgot password?
          </Link>
        </div>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Spinner />} Sign in
        </Button>
      </form>
    </AuthShell>
  )
}
