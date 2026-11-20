import { Link } from 'react-router-dom'
import {
  ArrowRight,
  BellRing,
  BookOpenCheck,
  Check,
  FileText,
  HeartPulse,
  Lock,
  MapPin,
  MessageSquareText,
  ShieldCheck,
  Siren,
  type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

const FEATURES: { icon: LucideIcon; title: string; body: string }[] = [
  { icon: MessageSquareText, title: 'Ask a health question', body: 'Type a question in your own words and get a clear answer, with the sources it came from. If we are not sure, we say so.' },
  { icon: FileText, title: 'Understand your lab results', body: 'Upload your lab report and see what each test means, and which results are outside the normal range printed on your report.' },
  { icon: HeartPulse, title: 'Do a 2-minute health check', body: 'Answer a few simple questions to see how you compare with thousands of other people, and whether a blood sugar test might be worth asking about.' },
  { icon: MapPin, title: 'Find care near you', body: 'See hospitals, clinics and pharmacies on a map, with phone numbers and directions.' },
  { icon: BellRing, title: 'Never miss a medicine', body: 'Add your medicines and times, then tick each dose off as you take it.' },
  { icon: Lock, title: 'Your information stays yours', body: 'We do not keep your lab files, we do not sell your data, and you can download or delete everything whenever you like.' },
]

const STEPS = [
  { n: '1', title: 'Create a free account', body: 'It takes about a minute. All you need is an email address.' },
  { n: '2', title: 'Ask, upload or check', body: 'Ask a question, upload a lab report, or answer the health check questions.' },
  { n: '3', title: 'Understand, then talk to a doctor', body: 'Use what you learn to feel more prepared when you speak to a doctor or pharmacist.' },
]

const SAFETY = [
  'MediCore is not a doctor. It cannot diagnose you or tell you which medicine to take.',
  'Answers come from trusted sources: the World Health Organization, the US CDC and PubMed. We show you each source.',
  'When our sources do not cover your question, we say so instead of guessing.',
  'It is not for emergencies. If you think you or someone else is in danger, call your local emergency number straight away.',
]

export default function Landing() {
  return (
    <>
      <section id="home" className="border-b bg-card">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 md:grid-cols-[1.15fr_0.85fr] md:py-24">
          <div className="space-y-6">
            <h1 className="text-4xl font-semibold leading-tight text-primary sm:text-5xl">Understand your health, in plain words.</h1>
            <p className="max-w-xl text-lg text-muted-foreground">
              Ask health questions, make sense of your lab results, and keep track of your medicines. Every answer shows where it came from.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button size="lg" asChild>
                <Link to="/register">
                  Get started free <ArrowRight />
                </Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <a href="#features">See what you can do</a>
              </Button>
            </div>
            <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted-foreground">
              {['Free to use', 'No jargon', 'Sources shown for every answer'].map((t) => (
                <li key={t} className="flex items-center gap-1.5">
                  <Check className="size-4 text-teal" /> {t}
                </li>
              ))}
            </ul>
          </div>
          <Card className="shadow-lg">
            <CardContent className="space-y-4 p-6">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">An example question</p>
              <div className="ml-auto w-fit max-w-[90%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
                What is the difference between HDL and LDL?
              </div>
              <div className="space-y-2 rounded-2xl rounded-bl-sm border bg-background px-4 py-3 text-sm">
                <p>
                  <strong>LDL</strong> is the “bad” cholesterol. Too much can build up in your arteries. <strong>HDL</strong> is the “good”
                  cholesterol. It helps carry extra cholesterol away.
                </p>
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <BookOpenCheck className="size-3.5 text-teal" /> Sources: World Health Organization, PubMed
                </p>
              </div>
              <p className="text-xs text-muted-foreground">This is an example of the style of answer. Real answers show their exact sources.</p>
            </CardContent>
          </Card>
        </div>
      </section>

      <section id="features" className="mx-auto max-w-6xl px-4 py-16">
        <div className="mb-10 max-w-2xl space-y-2">
          <h2 className="text-3xl font-semibold text-primary">What you can do</h2>
          <p className="text-muted-foreground">Everything is in one place, and everything is explained in everyday language.</p>
        </div>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <Card key={title} className="transition-shadow hover:shadow-md">
              <CardContent className="space-y-3 p-6">
                <span className="grid size-11 place-items-center rounded-xl bg-accent text-accent-foreground">
                  <Icon className="size-5" />
                </span>
                <h3 className="font-semibold">{title}</h3>
                <p className="text-sm text-muted-foreground">{body}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section id="how" className="border-y bg-card">
        <div className="mx-auto max-w-6xl px-4 py-16">
          <h2 className="mb-10 text-3xl font-semibold text-primary">How it works</h2>
          <ol className="grid gap-8 md:grid-cols-3">
            {STEPS.map((s) => (
              <li key={s.n} className="space-y-2">
                <span className="grid size-9 place-items-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">{s.n}</span>
                <h3 className="font-semibold">{s.title}</h3>
                <p className="text-sm text-muted-foreground">{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="safety" className="mx-auto grid max-w-6xl gap-10 px-4 py-16 md:grid-cols-2">
        <div className="space-y-4">
          <h2 className="text-3xl font-semibold text-primary">Your safety comes first</h2>
          <ul className="space-y-3">
            {SAFETY.map((t) => (
              <li key={t} className="flex gap-3 text-[15px]">
                <ShieldCheck className="mt-0.5 size-5 shrink-0 text-teal" />
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </div>
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="flex gap-4 p-6">
            <Siren className="mt-1 size-6 shrink-0 text-destructive" />
            <div className="space-y-2">
              <h3 className="font-semibold text-destructive">In an emergency, do not use this app</h3>
              <p className="text-sm">
                Call your local emergency number right away (for example 911 in the US, 112 in Europe, 999 in the UK) or go to the nearest emergency
                room. Signs like chest pain, trouble breathing, sudden weakness or confusion need help immediately.
              </p>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="border-t bg-card">
        <div className="mx-auto max-w-6xl space-y-4 px-4 py-14">
          <h2 className="text-2xl font-semibold text-primary">Ready to try it?</h2>
          <p className="text-muted-foreground">It is free and takes about a minute to set up.</p>
          <Button size="lg" asChild>
            <Link to="/register">
              Get started free <ArrowRight />
            </Link>
          </Button>
          <details className="pt-6 text-sm text-muted-foreground">
            <summary className="cursor-pointer font-medium text-foreground">For the curious: how is this built?</summary>
            <p className="mt-2 max-w-2xl">
              The Health Check is a machine-learning model trained on a public US health survey (CDC BRFSS 2015). Answers to questions come from a
              library of World Health Organization, US CDC and PubMed pages, found with semantic search, and the wording is checked against those
              sources. The app uses React, FastAPI and PostgreSQL. You can read the details on the{' '}
              <Link to="/register" className="underline">
                How it works
              </Link>{' '}
              page after you sign in.
            </p>
          </details>
        </div>
      </section>
    </>
  )
}
