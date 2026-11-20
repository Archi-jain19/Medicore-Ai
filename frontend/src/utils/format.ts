import type { RiskBand } from '@/types/api'

export const pct = (v: number | null | undefined, digits = 1) => (v == null ? '—' : `${(v * 100).toFixed(digits)}%`)
export const num = (v: number | null | undefined, digits = 3) => (v == null ? '—' : v.toFixed(digits))
export const int = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString())

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
export const shortDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

export const BAND_META: Record<RiskBand, { label: string; variant: 'success' | 'warning' | 'destructive'; color: string }> = {
  lower: { label: 'Lower chance', variant: 'success', color: 'var(--chart-2)' },
  elevated: { label: 'Higher chance', variant: 'warning', color: 'var(--chart-4)' },
  high: { label: 'Much higher chance', variant: 'destructive', color: 'var(--chart-5)' },
}

export const AGE_BANDS = ['18–24', '25–29', '30–34', '35–39', '40–44', '45–49', '50–54', '55–59', '60–64', '65–69', '70–74', '75–79', '80+']
export const GENHLTH = ['Excellent', 'Very good', 'Good', 'Fair', 'Poor']
