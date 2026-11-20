import { Link } from 'react-router-dom'
import { ContentPage, OPERATOR, Section } from '@/components/ContentPage'

const Contact = () =>
  OPERATOR.email ? (
    <>
      <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>
    </>
  ) : (
    <>the organisation that runs this service</>
  )

export function Privacy() {
  return (
    <ContentPage
      title="Privacy policy"
      intro="What we keep, what we do not, and the choices you have. We have tried to write this in plain words."
    >
      {OPERATOR.name && <p className="text-muted-foreground">This service is run by {OPERATOR.name}.</p>}

      <Section title="The short version">
        <ul>
          <li>Only you can see the information you save in MediCore.</li>
          <li>We do not keep the lab report files you upload. We keep only the results we read from them.</li>
          <li>We do not save your location.</li>
          <li>We do not sell your data and we do not show ads.</li>
          <li>You can download or delete your information at any time in Settings.</li>
        </ul>
      </Section>

      <Section title="What we keep">
        <ul>
          <li>
            <strong>Your account:</strong> your email address, your password (stored scrambled so nobody can read it), and your name if you give
            one.
          </li>
          <li>
            <strong>Your questions and the answers</strong> you were shown.
          </li>
          <li>
            <strong>Your lab results:</strong> the test names, numbers, units and normal ranges we read from a report, and a short summary. Not the
            file itself.
          </li>
          <li>
            <strong>Your health checks:</strong> the answers you gave and the result.
          </li>
          <li>
            <strong>Your medicine reminders</strong> and the doses you mark as taken or skipped.
          </li>
          <li>
            <strong>A list of your recent activity</strong>, such as “asked a question”, so you can see what you did.
          </li>
          <li>
            <strong>Technical records</strong> for security and fixing problems: the time of each request, your internet address and an error
            code. These do not contain your questions, answers or health details.
          </li>
        </ul>
      </Section>

      <Section title="Who else sees some of it">
        <ul>
          <li>
            <strong>AI writing.</strong> When AI writing is switched on, your question and the matching passages from our trusted sources are sent
            to Google’s Gemini service so it can write an answer. We do not send your name or email address. When it is off, nothing is sent.
          </li>
          <li>
            <strong>Maps.</strong> To find places, our server sends the place you typed, or your coordinates, to OpenStreetMap services. Your
            browser also downloads map pictures from OpenStreetMap, so they can see your internet address and the area you are viewing.
          </li>
          <li>
            <strong>Email.</strong> If you ask to reset your password, we send the email through our email provider.
          </li>
        </ul>
        <p>We do not share your information with anyone else, unless the law requires it.</p>
      </Section>

      <Section title="How long we keep it">
        <p>
          Until you delete it. In <Link to="/settings">Settings and privacy</Link> you can choose to have old history deleted automatically
          (after 30 days up to 1 year), delete parts of your data, or delete your whole account, which removes everything we saved about you. If
          the service keeps backups, deleted data can stay in those backups until they are replaced.
        </p>
      </Section>

      <Section title="Your choices">
        <ul>
          <li>See and download everything we hold about you: Settings and privacy, “Get a copy of my data”.</li>
          <li>Correct your name: Settings and privacy, “About you”.</li>
          <li>Delete data or your account: Settings and privacy.</li>
          <li>Ask us a question about your data: contact <Contact />.</li>
        </ul>
      </Section>

      <Section title="Keeping your information safe">
        <p>
          Passwords are stored in a scrambled form. Each person can only open their own records. Connections to the service should use HTTPS.
          No online service can promise perfect security, so please use a strong password that you do not use anywhere else.
        </p>
      </Section>

      <Section title="Age and sensitive information">
        <p>
          MediCore is for adults (18 and over). Health information is sensitive, so only enter what you are comfortable with. You never need to
          enter your own details in the Health Check to try it, because it has an “example answers” button.
        </p>
      </Section>

      <Section title="Changes and contact">
        <p>
          If we change this policy in a way that matters, we will tell you in the app. Questions? Contact <Contact />.
        </p>
      </Section>
    </ContentPage>
  )
}

export function Terms() {
  return (
    <ContentPage title="Terms of use" intro="The ground rules for using MediCore. Please read them before you create an account.">
      {OPERATOR.name && <p className="text-muted-foreground">This service is run by {OPERATOR.name}.</p>}

      <Section title="What MediCore is, and is not">
        <ul>
          <li>MediCore gives general health information in plain language. It is not a doctor and does not give medical advice.</li>
          <li>It cannot diagnose any condition, and it cannot tell you which medicine or dose to take.</li>
          <li>
            Results from the Health Check and the lab results explanations are information only. They can be wrong. Always talk to a doctor or
            pharmacist before making health decisions.
          </li>
          <li>
            <strong>It is not for emergencies.</strong> If you think someone is in danger, call your local emergency number straight away.
          </li>
        </ul>
      </Section>

      <Section title="Using the service">
        <ul>
          <li>You must be 18 or older.</li>
          <li>Give accurate information and keep your password private. You are responsible for what happens on your account.</li>
          <li>Only upload lab reports that are yours, or that you have permission to upload.</li>
          <li>Do not try to break, overload or misuse the service, or to get into other people’s accounts.</li>
        </ul>
      </Section>

      <Section title="Our promises, and their limits">
        <p>
          We work hard to keep the information accurate and the service running, but we cannot promise that answers are complete, up to date or
          free of mistakes, or that the service will always be available. The service is provided “as is”. To the extent the law allows, we are
          not responsible for decisions you make or harm that comes from relying on it.
        </p>
      </Section>

      <Section title="Your information">
        <p>
          How we handle your information is explained in our <Link to="/privacy">privacy policy</Link>.
        </p>
      </Section>

      <Section title="Ending your account">
        <p>
          You can delete your account at any time in Settings and privacy. We may suspend accounts that break these terms. We may update these
          terms, and we will tell you in the app when we make an important change.
        </p>
      </Section>

      <Section title="Contact">
        <p>
          Questions about these terms? Contact <Contact />.
        </p>
      </Section>
    </ContentPage>
  )
}
