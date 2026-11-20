import { z } from 'zod'

/** Mirrors backend rules in app/schemas/auth.py */
export const passwordSchema = z
  .string()
  .min(8, 'Use at least 8 characters')
  .max(72, 'Use 72 characters or fewer')
  .refine((v) => /[A-Za-z]/.test(v) && /\d/.test(v), 'Include at least one letter and one number')

export const loginSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(1, 'Please enter your password'),
})

export const registerSchema = z
  .object({
    full_name: z.string().max(120).optional(),
    email: z.string().email('Please enter a valid email address'),
    password: passwordSchema,
    confirm: z.string(),
    accept: z.literal(true, { errorMap: () => ({ message: 'Please tick this box to continue' }) }),
  })
  .refine((d) => d.password === d.confirm, { path: ['confirm'], message: 'Passwords do not match' })

export const forgotSchema = z.object({ email: z.string().email('Please enter a valid email address') })

export const resetSchema = z
  .object({ new_password: passwordSchema, confirm: z.string() })
  .refine((d) => d.new_password === d.confirm, { path: ['confirm'], message: 'Passwords do not match' })

export type LoginValues = z.infer<typeof loginSchema>
export type RegisterValues = z.infer<typeof registerSchema>
export type ForgotValues = z.infer<typeof forgotSchema>
export type ResetValues = z.infer<typeof resetSchema>
