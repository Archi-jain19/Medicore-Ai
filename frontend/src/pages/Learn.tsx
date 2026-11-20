import { Link } from 'react-router-dom'
import { ArrowRight, BarChart3, FlaskConical, Layers, Scale } from 'lucide-react'
import { ContentPage, Section } from '@/components/ContentPage'
import { Card, CardContent } from '@/components/ui/card'
import { useAuth } from '@/hooks/useAuth'

const DETAILS = [
  { to: '/learn/accuracy', icon: BarChart3, title: 'How accurate is the Health Check?', body: 'Test results, with a plain summary first.' },
  { to: '/explainability', icon: Scale, title: 'What affects the Health Check result?', body: 'Which answers matter most, and why.' },
  { to: '/learn/groups', icon: Layers, title: 'Patterns in the data', body: 'How the survey respondents group together.' },
  { to: '/assistant/evaluation', icon: FlaskConical, title: 'How we check our answers', body: 'How well we find and quote the right sources.' },
]

export default function Learn() {
  const { user } = useAuth()
  return (
    <ContentPage title="How it works" intro="A plain-language look at what happens behind the scenes, so you know what you can and cannot rely on.">
      <Section title="When you ask a question">
        <ol>
          <li>
            <strong>We search our library.</strong> It holds pages from the World Health Organization, the US CDC and PubMed (a database of
            medical research).
          </li>
          <li>
            <strong>We pick the best matches.</strong> We prefer trusted and recent sources, and we leave out anything that is not close to your
            question.
          </li>
          <li>
            <strong>We write a simple answer.</strong> It may only use what those sources say. If AI writing is switched off or busy, we
            quote the sources word for word instead.
          </li>
          <li>
            <strong>We check the answer.</strong> Each sentence is compared with the sources. Anything we cannot find in them is marked.
          </li>
          <li>
            <strong>We show our sources</strong>, with links, so you can read them yourself.
          </li>
        </ol>
        <p>
          If our library does not cover your question, we tell you instead of guessing. We never answer questions about your own diagnosis or
          which medicine to take.
        </p>
      </Section>

      <Section title="When you do a Health Check">
        <p>
          The Health Check was built from the answers of about 250,000 adults in a 2015 US health survey run by the CDC. Each person said
          whether they had diabetes or prediabetes, and answered questions about their health and habits. A computer program learned which
          answers tend to go together with diabetes.
        </p>
        <p>
          When you answer the same questions, it finds how many people out of 100 with answers like yours said they had diabetes or prediabetes.
          That is the “about N in 100” you see.
        </p>
        <p>
          <strong>What it cannot do:</strong> it does not use blood tests, it cannot say what is causing anything, and it was built from one
          country in one year, so it may be less accurate for other people. It is meant to nudge you to ask about a blood sugar test, not to tell
          you whether you have diabetes.
        </p>
      </Section>

      <Section title="When you upload a lab report">
        <p>
          We read the text in your file (or use text recognition for a photo) and look for test names, numbers, units and the normal range
          printed beside each one. We compare each result only with the range on your own report, because different labs use different ranges.
          We do not keep your file. We save only the results, so you can look at them later, and you can delete them whenever you like.
        </p>
      </Section>

      <Section title="For the curious">
        {user ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {DETAILS.map(({ to, icon: Icon, title, body }) => (
              <Link key={to} to={to} className="group">
                <Card className="h-full transition-shadow group-hover:shadow-md">
                  <CardContent className="space-y-2 p-4">
                    <Icon className="size-5 text-teal" />
                    <p className="font-medium text-primary">{title}</p>
                    <p className="text-sm text-muted-foreground">{body}</p>
                    <span className="flex items-center gap-1 text-sm font-medium text-primary">
                      Read more <ArrowRight className="size-4" />
                    </span>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        ) : (
          <p>
            <Link to="/register">Create a free account</Link> or <Link to="/login">sign in</Link> to see the detailed numbers, such as how
            accurate the Health Check was in testing.
          </p>
        )}
      </Section>
    </ContentPage>
  )
}
