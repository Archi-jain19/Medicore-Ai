import type { PatientInput } from '@/types/api'

/**
 * The Health Check questions, in everyday words. The `key` is the field the model was trained on
 * (CDC BRFSS 2015 survey); only the wording shown to people changes here.
 */
export type FieldDef =
  | { key: keyof PatientInput; kind: 'yesno'; label: string; help?: string; yes?: string; no?: string }
  | { key: keyof PatientInput; kind: 'select'; label: string; help?: string; options: { value: number; label: string }[] }
  | { key: keyof PatientInput; kind: 'number'; label: string; help?: string; min: number; max: number; step?: number }

const opts = (labels: string[]) => labels.map((label, i) => ({ value: i + 1, label }))

export const FIELD_GROUPS: { title: string; hint?: string; fields: FieldDef[] }[] = [
  {
    title: 'About you',
    fields: [
      {
        key: 'Age',
        kind: 'select',
        label: 'How old are you?',
        options: opts(['18 to 24', '25 to 29', '30 to 34', '35 to 39', '40 to 44', '45 to 49', '50 to 54', '55 to 59', '60 to 64', '65 to 69', '70 to 74', '75 to 79', '80 or older']),
      },
      { key: 'Sex', kind: 'yesno', label: 'Are you male or female?', help: 'The survey behind this check only recorded these two options.', yes: 'Male', no: 'Female' },
      {
        key: 'Education',
        kind: 'select',
        label: 'What is the highest level of school you finished?',
        options: opts(['Never went to school', 'Primary school', 'Some secondary school', 'Finished secondary school', 'Some college or training', 'College graduate']),
      },
      {
        key: 'Income',
        kind: 'select',
        label: 'About how much does your household earn in a year?',
        help: 'In US dollars. It is fine to pick the closest.',
        options: opts(['Under $10,000', '$10,000 to $15,000', '$15,000 to $20,000', '$20,000 to $25,000', '$25,000 to $35,000', '$35,000 to $50,000', '$50,000 to $75,000', '$75,000 or more']),
      },
    ],
  },
  {
    title: 'Your health right now',
    fields: [
      { key: 'BMI', kind: 'number', label: 'What is your BMI?', min: 12, max: 98, step: 0.1, help: 'BMI compares your weight with your height. Not sure? Use the height and weight helper below.' },
      { key: 'GenHlth', kind: 'select', label: 'In general, how is your health?', options: opts(['Excellent', 'Very good', 'Good', 'Fair', 'Poor']) },
      { key: 'MentHlth', kind: 'number', label: 'In the last 30 days, on how many days was your mental health not good?', min: 0, max: 30, help: 'Think of stress, low mood or difficult emotions. Enter 0 if none.' },
      { key: 'PhysHlth', kind: 'number', label: 'In the last 30 days, on how many days was your physical health not good?', min: 0, max: 30, help: 'Think of illness or injury. Enter 0 if none.' },
      { key: 'DiffWalk', kind: 'yesno', label: 'Do you have serious trouble walking or climbing stairs?' },
    ],
  },
  {
    title: 'Health problems a doctor has told you about',
    fields: [
      { key: 'HighBP', kind: 'yesno', label: 'Has a doctor ever told you that you have high blood pressure?' },
      { key: 'HighChol', kind: 'yesno', label: 'Has a doctor ever told you that you have high cholesterol?' },
      { key: 'CholCheck', kind: 'yesno', label: 'Have you had your cholesterol checked in the last 5 years?' },
      { key: 'Stroke', kind: 'yesno', label: 'Have you ever had a stroke?' },
      { key: 'HeartDiseaseorAttack', kind: 'yesno', label: 'Have you ever had heart disease or a heart attack?' },
    ],
  },
  {
    title: 'Daily habits and care',
    fields: [
      { key: 'PhysActivity', kind: 'yesno', label: 'In the last 30 days, did you do any exercise outside of your job?', help: 'Like walking, running, cycling or sports.' },
      { key: 'Fruits', kind: 'yesno', label: 'Do you eat fruit at least once a day?' },
      { key: 'Veggies', kind: 'yesno', label: 'Do you eat vegetables at least once a day?' },
      { key: 'Smoker', kind: 'yesno', label: 'Have you smoked at least 100 cigarettes in your life?', help: 'That is about 5 packs.' },
      { key: 'HvyAlcoholConsump', kind: 'yesno', label: 'Do you drink a lot of alcohol?', help: 'For men, more than 14 drinks a week. For women, more than 7.' },
      { key: 'AnyHealthcare', kind: 'yesno', label: 'Do you have health insurance or another kind of health coverage?' },
      { key: 'NoDocbcCost', kind: 'yesno', label: 'In the last year, was there a time you needed a doctor but could not go because of the cost?' },
    ],
  },
]

export const ALL_FIELDS = FIELD_GROUPS.flatMap((g) => g.fields)

/** Example answers, used by the "Try with example answers" button so people can see how a result looks. */
export const EXAMPLE_INPUT: PatientInput = {
  HighBP: 0, HighChol: 0, CholCheck: 1, BMI: 27, Smoker: 0, Stroke: 0, HeartDiseaseorAttack: 0, PhysActivity: 1,
  Fruits: 1, Veggies: 1, HvyAlcoholConsump: 0, AnyHealthcare: 1, NoDocbcCost: 0, GenHlth: 3, MentHlth: 0,
  PhysHlth: 0, DiffWalk: 0, Sex: 0, Age: 7, Education: 5, Income: 6,
}

/** BMI = kg / m². Accepts metric (cm, kg) or imperial (ft+in, lb). Returns null for impossible inputs. */
export function computeBmi(height: { cm?: number; ft?: number; inch?: number }, weight: { kg?: number; lb?: number }): number | null {
  const metres = height.cm != null ? height.cm / 100 : ((height.ft ?? 0) * 12 + (height.inch ?? 0)) * 0.0254
  const kg = weight.kg != null ? weight.kg : (weight.lb ?? 0) * 0.45359237
  if (!(metres > 0.9 && metres < 2.6 && kg > 25 && kg < 400)) return null
  return Math.round((kg / (metres * metres)) * 10) / 10
}
