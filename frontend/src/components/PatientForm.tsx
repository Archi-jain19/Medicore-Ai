import { useState } from 'react'
import { useForm, type UseFormSetValue } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Input, Select } from '@/components/ui/input'
import { FormField, Spinner } from '@/components/ui/misc'
import type { PatientInput } from '@/types/api'
import { ALL_FIELDS, EXAMPLE_INPUT, FIELD_GROUPS, computeBmi } from '@/utils/features'

const CHOOSE = 'Please choose an answer'
/** A blank answer must be "missing", never silently 0 (z.coerce would turn '' into 0 or NaN before any rule runs). */
const toNumber = (v: unknown) => (v === '' || v == null ? undefined : Number(v))
const num = (min: number, max: number, whole = false, minMsg = `Enter a number from ${min} to ${max}`) => {
  let n = z.number({ required_error: 'Please enter a number', invalid_type_error: 'Please enter a number' }).min(min, minMsg).max(max, `Enter a number from ${min} to ${max}`)
  if (whole) n = n.int('Enter a whole number')
  return z.preprocess(toNumber, n)
}
const choice = (min: number, max: number) =>
  z.preprocess(toNumber, z.number({ required_error: CHOOSE, invalid_type_error: CHOOSE }).int(CHOOSE).min(min, CHOOSE).max(max, CHOOSE))
const yesno = choice(0, 1)

const schema = z.object({
  HighBP: yesno, HighChol: yesno, CholCheck: yesno, Smoker: yesno, Stroke: yesno, HeartDiseaseorAttack: yesno,
  PhysActivity: yesno, Fruits: yesno, Veggies: yesno, HvyAlcoholConsump: yesno, AnyHealthcare: yesno,
  NoDocbcCost: yesno, DiffWalk: yesno, Sex: yesno,
  BMI: num(12, 98, false, 'That BMI looks too low. Please check it, or use the helper below'),
  GenHlth: choice(1, 5), MentHlth: num(0, 30, true), PhysHlth: num(0, 30, true),
  Age: choice(1, 13), Education: choice(1, 6), Income: choice(1, 8),
})

function BmiHelper({ setValue }: { setValue: UseFormSetValue<PatientInput> }) {
  const [units, setUnits] = useState<'metric' | 'imperial'>('metric')
  const [h, setH] = useState({ cm: '', ft: '', inch: '' })
  const [w, setW] = useState({ kg: '', lb: '' })
  const [msg, setMsg] = useState<string | null>(null)
  const apply = () => {
    const bmi =
      units === 'metric'
        ? computeBmi({ cm: Number(h.cm) }, { kg: Number(w.kg) })
        : computeBmi({ ft: Number(h.ft), inch: Number(h.inch || 0) }, { lb: Number(w.lb) })
    if (bmi == null) return setMsg('Please check your height and weight.')
    setValue('BMI', bmi, { shouldValidate: true, shouldDirty: true })
    setMsg(`Your BMI is ${bmi}. We filled it in above.`)
  }
  return (
    <details className="rounded-lg border bg-secondary/40 px-3 py-2 text-sm sm:col-span-2">
      <summary className="cursor-pointer font-medium">Not sure of your BMI? Work it out from your height and weight</summary>
      <div className="mt-3 grid gap-3 sm:grid-cols-[auto_1fr_1fr_auto] sm:items-end">
        <Select aria-label="Units" value={units} onChange={(e) => setUnits(e.target.value as 'metric' | 'imperial')} className="w-36">
          <option value="metric">Metric (cm, kg)</option>
          <option value="imperial">US (feet, pounds)</option>
        </Select>
        {units === 'metric' ? (
          <>
            <FormField id="bmi_cm" label="Height (cm)">
              <Input id="bmi_cm" inputMode="decimal" value={h.cm} onChange={(e) => setH({ ...h, cm: e.target.value })} />
            </FormField>
            <FormField id="bmi_kg" label="Weight (kg)">
              <Input id="bmi_kg" inputMode="decimal" value={w.kg} onChange={(e) => setW({ ...w, kg: e.target.value })} />
            </FormField>
          </>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              <FormField id="bmi_ft" label="Feet">
                <Input id="bmi_ft" inputMode="numeric" value={h.ft} onChange={(e) => setH({ ...h, ft: e.target.value })} />
              </FormField>
              <FormField id="bmi_in" label="Inches">
                <Input id="bmi_in" inputMode="numeric" value={h.inch} onChange={(e) => setH({ ...h, inch: e.target.value })} />
              </FormField>
            </div>
            <FormField id="bmi_lb" label="Weight (pounds)">
              <Input id="bmi_lb" inputMode="decimal" value={w.lb} onChange={(e) => setW({ ...w, lb: e.target.value })} />
            </FormField>
          </>
        )}
        <Button type="button" variant="outline" onClick={apply}>
          Work out my BMI
        </Button>
      </div>
      {msg && <p className="mt-2 text-xs text-muted-foreground" role="status">{msg}</p>}
    </details>
  )
}

export function PatientForm({
  onSubmit,
  submitLabel = 'See my result',
  showExample = true,
}: {
  onSubmit: (v: PatientInput) => Promise<void> | void
  submitLabel?: string
  showExample?: boolean
}) {
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors, isSubmitting, submitCount },
  } = useForm<PatientInput>({ resolver: zodResolver(schema) as never, defaultValues: {} })
  const answered = ALL_FIELDS.filter((f) => {
    const v = watch(f.key) as unknown
    return v !== undefined && v !== '' && v !== null && !Number.isNaN(v)
  }).length
  const missing = Object.keys(errors).length

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-7" noValidate>
      {FIELD_GROUPS.map((g) => (
        <fieldset key={g.title} className="space-y-3">
          <legend className="text-base font-semibold text-primary">{g.title}</legend>
          <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
            {g.fields.map((f) => {
              const err = errors[f.key]?.message as string | undefined
              return (
                <div key={f.key} className="contents">
                  <FormField id={f.key} label={f.label} error={err} hint={f.help}>
                    {f.kind === 'number' ? (
                      <Input id={f.key} type="number" inputMode="decimal" min={f.min} max={f.max} step={f.step ?? 1} aria-invalid={!!err} {...register(f.key)} />
                    ) : f.kind === 'select' ? (
                      <Select id={f.key} aria-invalid={!!err} defaultValue="" {...register(f.key)}>
                        <option value="" disabled>
                          Choose…
                        </option>
                        {f.options.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <Select id={f.key} aria-invalid={!!err} defaultValue="" {...register(f.key)}>
                        <option value="" disabled>
                          Choose…
                        </option>
                        <option value={1}>{f.yes ?? 'Yes'}</option>
                        <option value={0}>{f.no ?? 'No'}</option>
                      </Select>
                    )}
                  </FormField>
                  {f.key === 'BMI' && <BmiHelper setValue={setValue} />}
                </div>
              )
            })}
          </div>
        </fieldset>
      ))}
      {submitCount > 0 && missing > 0 && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {missing === 1 ? '1 question still needs an answer.' : `${missing} questions still need an answer.`} They are marked above.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="lg" disabled={isSubmitting}>
          {isSubmitting && <Spinner />} {submitLabel}
        </Button>
        {showExample && (
          <Button type="button" variant="ghost" onClick={() => reset(EXAMPLE_INPUT)}>
            Try with example answers
          </Button>
        )}
        <span className="text-xs text-muted-foreground">
          {answered} of {ALL_FIELDS.length} answered
        </span>
      </div>
    </form>
  )
}
