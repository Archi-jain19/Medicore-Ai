import { Link } from 'react-router-dom'
import { Siren } from 'lucide-react'
import { Alert } from '@/components/ui/alert'
import { ContentPage, Faq, OPERATOR, Section } from '@/components/ContentPage'

const EMERGENCY = [
  ['United States and Canada', '911'],
  ['European Union', '112'],
  ['United Kingdom', '999 (or 112)'],
  ['India', '112 (ambulance: 108 in many states)'],
  ['Australia', '000'],
  ['New Zealand', '111'],
]

export default function Help() {
  return (
    <ContentPage title="Help and safety" intro="Answers to common questions, and what to do if something does not work.">
      <Alert variant="destructive">
        <Siren />
        <div className="space-y-2">
          <p className="font-medium">In an emergency, call your local emergency number. Do not use this app.</p>
          <p className="text-sm">
            Chest pain, trouble breathing, signs of a stroke (face drooping, weak arm, slurred speech), heavy bleeding, thoughts of harming
            yourself, or someone who is unconscious all need help right now.
          </p>
          <table className="text-sm">
            <tbody>
              {EMERGENCY.map(([place, num]) => (
                <tr key={place}>
                  <td className="pr-4">{place}</td>
                  <td className="font-semibold">{num}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs">If your country is not listed, search for “emergency number” and your country name.</p>
        </div>
      </Alert>

      <Section title="About MediCore">
        <div className="space-y-2">
          <Faq q="Is MediCore a doctor?">
            <p>
              No. MediCore gives health information in plain words to help you understand things better. It cannot examine you, diagnose you, or
              tell you which medicine to take. Please talk to a doctor or pharmacist about your own health.
            </p>
          </Faq>
          <Faq q="Where do the answers come from?">
            <p>
              From trusted public sources: the World Health Organization (WHO), the US Centers for Disease Control and Prevention (CDC), and
              PubMed, which lists medical research. Every answer shows the sources it used, with links, so you can read them yourself.
            </p>
          </Faq>
          <Faq q="Can an answer be wrong?">
            <p>
              Yes. Sources can be out of date, and we can pick the wrong part of a source. After each answer we check every sentence against the
              sources and mark any sentence we cannot find in them. Even so, please treat answers as a starting point and check important things
              with a doctor or pharmacist.
            </p>
          </Faq>
          <Faq q="What if you cannot find an answer?">
            <p>
              We will say so instead of guessing. Try asking in different words, or ask a doctor or pharmacist.
            </p>
          </Faq>
          <Faq q="Does it work in other languages?">
            <p>Not yet. MediCore currently works in English only.</p>
          </Faq>
          <Faq q="Who is it for?">
            <p>Adults who want to understand health information better. It is not meant for children, and it is not a replacement for medical care.</p>
          </Faq>
        </div>
      </Section>

      <Section title="Using the features">
        <div className="space-y-2">
          <Faq q="What does the Health Check tell me?">
            <p>
              It compares your answers with a large US health survey and tells you roughly how many people out of 100 with similar answers said
              they have diabetes or prediabetes. It also tells you what to do next, such as asking about a blood sugar test.
            </p>
            <p>
              It is <strong>not a diagnosis</strong>. It does not use a blood test, so it can miss some people and raise a false alarm for others.
              See <Link to="/learn">how it works</Link> for details.
            </p>
          </Faq>
          <Faq q="One of my lab results is outside the normal range. Should I worry?">
            <p>
              Not necessarily. Many things can change a result, like what you ate or how you felt that day. We compare each result with the normal
              range printed on your own report, because ranges are different from lab to lab. Please go through your results with a doctor.
            </p>
          </Faq>
          <Faq q="My lab report would not upload, or the results look wrong">
            <ul>
              <li>Use a PDF where you can select the text, or a clear, well-lit photo of the whole page.</li>
              <li>The file must be a PDF, JPG or PNG, under 10 MB. PDFs can have up to 20 pages.</li>
              <li>PDFs with a password must have the password removed first.</li>
              <li>Some report layouts are hard to read. If we miss a result, please check it on your original report.</li>
            </ul>
          </Faq>
          <Faq q="Why can I not find places near me?">
            <ul>
              <li>Check that you allowed your browser to share your location, or type a city or address instead.</li>
              <li>Try looking further away. Our map has more detail in some areas than others.</li>
              <li>If you see a message that the map service is busy, wait a minute and try again.</li>
            </ul>
          </Faq>
          <Faq q="Will I get a reminder when it is time for my medicine?">
            <p>
              You will see a pop-up while MediCore is open in your web browser, if you turn alerts on. We do not send emails, texts or phone
              notifications yet, so please do not rely on MediCore as your only reminder.
            </p>
          </Faq>
        </div>
      </Section>

      <Section title="Your account and data">
        <div className="space-y-2">
          <Faq q="I forgot my password">
            <p>
              Go to the <Link to="/forgot-password">password reset page</Link>, enter your email, and we will send you a link that works for 15
              minutes. If you do not see the email, check your spam folder.
            </p>
          </Faq>
          <Faq q="Is my information private?">
            <p>
              Only you can see what you save. We do not keep the lab files you upload, we do not save your location, and we do not sell your data.
              Read the <Link to="/privacy">privacy policy</Link> for the details.
            </p>
          </Faq>
          <Faq q="How do I download or delete my data?">
            <p>
              Go to <Link to="/settings">Settings and privacy</Link>. You can download a copy of everything, delete parts of your data, set old
              history to delete itself, or delete your whole account.
            </p>
          </Faq>
        </div>
      </Section>

      <Section title="Still stuck?">
        {OPERATOR.email ? (
          <p>
            Email us at <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>. Please do not include your medical details in the email.
          </p>
        ) : (
          <p>If you cannot solve a problem here, please contact the organisation that gave you access to MediCore.</p>
        )}
      </Section>
    </ContentPage>
  )
}
