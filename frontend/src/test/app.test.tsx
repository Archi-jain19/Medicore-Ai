import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ContributionChart } from '@/components/charts/ContributionChart'
import { FactorList } from '@/components/FactorList'
import { PatientForm } from '@/components/PatientForm'
import { PeopleGrid } from '@/components/PeopleGrid'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { AuthProvider } from '@/context/AuthContext'
import { AppLayout } from '@/layouts/AppLayout'
import Landing from '@/pages/Landing'
import Login from '@/pages/auth/Login'
import Register from '@/pages/auth/Register'
import { api, errorMessage, TOKEN_KEY } from '@/services/api'
import { computeBmi, EXAMPLE_INPUT } from '@/utils/features'
import { passwordSchema } from '@/utils/validation'

// Recharts' ResponsiveContainer needs ResizeObserver in jsdom
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver
Element.prototype.scrollIntoView = vi.fn()

function withProviders(ui: React.ReactNode, path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>,
  )
}

const PROFILE = { email: 'sam@example.com', full_name: 'Sam Lee', notify_reminders: true, data_retention_days: null, created_at: new Date().toISOString() }

/** Minimal fake API so whole pages can render. */
function mockApi(overrides: Record<string, unknown> = {}) {
  const table: Record<string, unknown> = {
    '/auth/me': { id: 1, email: 'sam@example.com', full_name: 'Sam Lee', created_at: '' },
    '/dashboard/summary': { user: { email: 'sam@example.com', full_name: 'Sam Lee' }, counts: { reports: 0, conversations: 0, predictions: 0, active_reminders: 0 }, my_risk_distribution: [], my_prediction_trend: [], recent_activity: [] },
    '/users/me/profile': PROFILE,
    '/rag/status': { knowledge_base_built: true, generation_configured: false, generation_model: null, embedding_model: 'x', chunks: 10, documents_by_source: {}, built_at: null },
    ...overrides,
  }
  return vi.spyOn(api, 'get').mockImplementation(async (url: string) => {
    const key = Object.keys(table).find((k) => url.startsWith(k))
    return { data: key ? table[key] : [] } as never
  })
}

/** Words that mean nothing to most people. They may appear only inside optional "details" sections. */
const JARGON = [/SHAP/, /calibrat/i, /\bRAG\b/, /\bOCR\b/, /threshold/i, /model estimate/i, /knowledge base/i, /\bAPI\b/, /\bpredictive\b/i, /heuristic/i, /\bk-?means\b/i, /embedding/i]
function expectNoJargon() {
  const copy = document.body.cloneNode(true) as HTMLElement
  copy.querySelectorAll('details, [data-technical]').forEach((n) => n.remove())
  const text = copy.textContent ?? ''
  const found = JARGON.filter((re) => re.test(text)).map(String)
  expect(found, `jargon found in: ${text.slice(0, 200)}…`).toEqual([])
}

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('validation', () => {
  it('matches backend password rules', () => {
    expect(passwordSchema.safeParse('short1').success).toBe(false)
    expect(passwordSchema.safeParse('onlyletters').success).toBe(false)
    expect(passwordSchema.safeParse('Passw0rd!').success).toBe(true)
  })
})

describe('errorMessage', () => {
  const axiosError = (response?: object) => Object.assign(new Error('x'), { isAxiosError: true, response })
  it('shows the server message when there is one', () => {
    const err = axiosError({ status: 409, data: { error: { code: 'conflict', message: 'There is already an account with this email.' } } })
    expect(errorMessage(err)).toBe('There is already an account with this email.')
  })
  it('explains connection problems in plain words', () => {
    expect(errorMessage(axiosError())).toMatch(/cannot connect right now/i)
  })
  it('hides technical field errors', () => {
    const err = axiosError({ status: 422, data: { error: { code: 'validation_error', message: 'x', details: [{ field: 'password', message: 'String should have at least 8 characters' }] } } })
    expect(errorMessage(err)).toBe('Some of the information you entered is not valid. Please check it and try again.')
  })
  it('does not leak server failures', () => {
    expect(errorMessage(axiosError({ status: 500, data: {} }))).toMatch(/on our side/)
  })
})

describe('Landing', () => {
  it('speaks plainly and has clear calls to action', () => {
    withProviders(<Landing />)
    expect(screen.getByRole('heading', { name: 'Understand your health, in plain words.' })).toBeInTheDocument()
    for (const link of screen.getAllByRole('link', { name: /Get started free/ })) expect(link).toHaveAttribute('href', '/register')
    expect(screen.getByRole('link', { name: /See what you can do/ })).toHaveAttribute('href', '#features')
    expect(screen.getByText(/In an emergency, do not use this app/)).toBeInTheDocument()
    expectNoJargon()
  })
})

describe('ProtectedRoute', () => {
  it('redirects anonymous users to /login', async () => {
    withProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<p>secret</p>} />
        </Route>
        <Route path="/login" element={<p>login page</p>} />
      </Routes>,
      '/dashboard',
    )
    expect(await screen.findByText('login page')).toBeInTheDocument()
    expect(screen.queryByText('secret')).not.toBeInTheDocument()
  })
})

describe('Login', () => {
  it('shows field validation without calling the API', async () => {
    const post = vi.spyOn(api, 'post')
    withProviders(<Login />, '/login')
    await userEvent.click(await screen.findByRole('button', { name: /Sign in/ }))
    expect(await screen.findByText('Please enter a valid email address')).toBeInTheDocument()
    expect(post).not.toHaveBeenCalled()
  })

  it('stores the token on success and surfaces server errors', async () => {
    const post = vi.spyOn(api, 'post').mockRejectedValueOnce(
      Object.assign(new Error('401'), {
        isAxiosError: true,
        response: { status: 401, data: { error: { code: 'unauthorized', message: 'Incorrect email or password' } } },
      }),
    )
    withProviders(<Login />, '/login')
    await userEvent.type(await screen.findByLabelText('Email'), 'a@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'Passw0rd!')
    await userEvent.click(screen.getByRole('button', { name: /Sign in/ }))
    expect(await screen.findByText('Incorrect email or password')).toBeInTheDocument()

    post.mockResolvedValueOnce({ data: { access_token: 'tok', token_type: 'bearer', expires_in: 3600 } })
    vi.spyOn(api, 'get').mockResolvedValueOnce({ data: { id: 1, email: 'a@example.com', full_name: null, created_at: '' } })
    await userEvent.click(screen.getByRole('button', { name: /Sign in/ }))
    await waitFor(() => expect(localStorage.getItem(TOKEN_KEY)).toBe('tok'))
  })
})

describe('Register', () => {
  it('asks for agreement to the terms, links to them, and checks the passwords match', async () => {
    withProviders(<Register />, '/register')
    expect(screen.getByRole('link', { name: 'Terms of use' })).toHaveAttribute('href', '/terms')
    expect(screen.getByRole('link', { name: 'Privacy policy' })).toHaveAttribute('href', '/privacy')
    await userEvent.type(await screen.findByLabelText('Email'), 'a@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'Passw0rd!')
    await userEvent.type(screen.getByLabelText('Confirm password'), 'Different1')
    await userEvent.click(screen.getByRole('button', { name: /Create account/ }))
    expect(await screen.findByText('Please tick this box to continue')).toBeInTheDocument()
    // The cross-field check runs once individual fields are valid
    await userEvent.click(screen.getByRole('checkbox'))
    await userEvent.click(screen.getByRole('button', { name: /Create account/ }))
    expect(await screen.findByText('Passwords do not match')).toBeInTheDocument()
  })
})

describe('computeBmi', () => {
  it('works from metric and US units, and rejects impossible values', () => {
    expect(computeBmi({ cm: 170 }, { kg: 70 })).toBe(24.2)
    expect(computeBmi({ ft: 5, inch: 7 }, { lb: 154 })).toBe(24.1)
    expect(computeBmi({ cm: 17 }, { kg: 70 })).toBeNull()
    expect(computeBmi({ cm: 170 }, { kg: 5 })).toBeNull()
  })
})

describe('PatientForm (Health Check questions)', () => {
  it('asks plain questions and starts with nothing pre-answered', () => {
    render(<PatientForm onSubmit={vi.fn()} />)
    expect(screen.getByLabelText('Has a doctor ever told you that you have high blood pressure?')).toHaveValue('')
    expect(screen.getByText('0 of 21 answered')).toBeInTheDocument()
  })

  it('will not submit until every question is answered', async () => {
    const onSubmit = vi.fn()
    render(<PatientForm onSubmit={onSubmit} />)
    await userEvent.click(screen.getByRole('button', { name: /See my result/ }))
    expect((await screen.findAllByText('Please choose an answer')).length).toBeGreaterThan(10)
    expect(screen.getByRole('alert')).toHaveTextContent(/questions still need an answer/)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits whole-number answers in the shape the API expects', async () => {
    const onSubmit = vi.fn()
    render(<PatientForm onSubmit={onSubmit} />)
    await userEvent.click(screen.getByRole('button', { name: 'Try with example answers' }))
    const bmi = screen.getByLabelText('What is your BMI?')
    await userEvent.clear(bmi)
    await userEvent.type(bmi, '31.5')
    await userEvent.click(screen.getByRole('button', { name: /See my result/ }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    const payload = onSubmit.mock.calls[0][0]
    expect(payload).toEqual({ ...EXAMPLE_INPUT, BMI: 31.5 })
    expect(Object.values(payload).every((v) => typeof v === 'number')).toBe(true)
  })

  it('rejects out-of-range numbers with a friendly message', async () => {
    const onSubmit = vi.fn()
    render(<PatientForm onSubmit={onSubmit} />)
    await userEvent.click(screen.getByRole('button', { name: 'Try with example answers' }))
    const days = screen.getByLabelText(/mental health not good/)
    await userEvent.clear(days)
    await userEvent.type(days, '45')
    await userEvent.click(screen.getByRole('button', { name: /See my result/ }))
    expect(await screen.findByText('Enter a number from 0 to 30')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('works out BMI from height and weight', async () => {
    render(<PatientForm onSubmit={vi.fn()} />)
    await userEvent.click(screen.getByText(/Not sure of your BMI/))
    await userEvent.type(screen.getByLabelText('Height (cm)'), '170')
    await userEvent.type(screen.getByLabelText('Weight (kg)'), '70')
    await userEvent.click(screen.getByRole('button', { name: 'Work out my BMI' }))
    expect(screen.getByLabelText('What is your BMI?')).toHaveValue(24.2)
    expect(screen.getByRole('status')).toHaveTextContent('Your BMI is 24.2')
  })
})

describe('Health Check result', () => {
  const result = {
    id: 1, predicted_class: 1, predicted_label: 'Worth a blood sugar test', headline: 'Your answers point to a higher-than-average chance',
    chance_text: 'about 18 in 100', next_step: 'A simple blood sugar test from a doctor or pharmacist can tell for sure.', probability: 0.18, threshold: 0.12,
    risk_band: 'elevated', population_base_rate: 0.139, model_name: 'diabetes_risk', model_version: '1.0.0', algorithm: 'XGBoost',
    top_contributions: [
      { feature: 'GenHlth', label: 'x', value: 4, shap_value: 0.5, direction: 'increases', plain_label: 'How you rate your overall health', plain_value: 'Fair' },
      { feature: 'PhysActivity', label: 'y', value: 1, shap_value: -0.2, direction: 'decreases', plain_label: 'Exercised in the last month', plain_value: 'Yes' },
    ],
    explanation: 'About 18 in 100 people with answers like yours said they have diabetes or prediabetes.',
    limitations: ['This is not a diagnosis. Only a blood test from a doctor or pharmacist can show whether someone has diabetes.'], created_at: '',
  }

  it('shows the result in everyday words, with a next step and no jargon outside the details section', async () => {
    mockApi()
    vi.spyOn(api, 'post').mockResolvedValue({ data: result })
    const { default: HealthCheck } = await import('@/pages/HealthCheck')
    withProviders(<HealthCheck />, '/analytics')
    await userEvent.click(await screen.findByRole('button', { name: 'Try with example answers' }))
    await userEvent.click(screen.getByRole('button', { name: /See my result/ }))
    expect(await screen.findByText('Your answers point to a higher-than-average chance')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /about 18 in 100/ })).toBeInTheDocument()
    expect(screen.getByText('How you rate your overall health')).toBeInTheDocument()
    expect(screen.getByText('Fair')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Find a pharmacy or clinic near me/ })).toHaveAttribute('href', '/locator?category=pharmacy')
    expect(screen.getAllByText(/not a diagnosis/i).length).toBeGreaterThan(0)
    expectNoJargon()
  })
})

describe('FactorList and PeopleGrid', () => {
  it('shows what raised and lowered a result in plain words', () => {
    render(
      <FactorList
        data={[
          { feature: 'BMI', label: 'BMI', value: 34, shap_value: 0.4, direction: 'increases', plain_label: 'Your weight for your height (BMI)', plain_value: '34' },
          { feature: 'PhysActivity', label: 'p', value: 1, shap_value: -0.1, direction: 'decreases', plain_label: 'Exercised in the last month', plain_value: 'Yes' },
        ]}
      />,
    )
    expect(screen.getByText('Pushed your result up')).toBeInTheDocument()
    expect(screen.getByText('Pulled your result down')).toBeInTheDocument()
    expect(screen.getByText('Your weight for your height (BMI)')).toBeInTheDocument()
  })
  it('draws 100 people', () => {
    const { container } = render(<PeopleGrid filled={18} label="about 18 in 100" />)
    expect(screen.getByRole('img', { name: 'about 18 in 100' })).toBeInTheDocument()
    expect(container.querySelectorAll('circle')).toHaveLength(100)
  })
})

describe('ContributionChart (details view)', () => {
  it('renders the direction legend in plain words', () => {
    render(<ContributionChart data={[{ feature: 'BMI', label: 'Body mass index', value: 34, shap_value: 0.4, direction: 'increases' }]} />)
    expect(screen.getByText('Pushed the result up')).toBeInTheDocument()
    expect(screen.getByText('Pulled the result down')).toBeInTheDocument()
  })
})

describe('MessageBubble', () => {
  const source = {
    rank: 1, chunk_id: 'who:hypertension#0', doc_id: 'who:hypertension', title: 'WHO fact sheet: Hypertension', source: 'WHO', doc_type: 'fact_sheet',
    url: 'https://www.who.int/x', published: '2025-09-25', snippet: 'passage', relevance: 0.71,
    score_breakdown: { similarity: 0.6, source_reliability: 1, recency: 0.95, clinical_relevance: 0.5 },
  }

  it('renders the answer, friendly source details, and flags statements that were not found in the sources', async () => {
    const { MessageBubble } = await import('@/components/assistant/MessageBubble')
    render(
      <MessageBubble
        m={{
          id: 1, role: 'assistant', content: 'Hypertension is **high blood pressure** [1].', created_at: '', retrieval_strategy: 'adaptive', status: 'ok', sources: [source],
          verification: { claims: [{ text: 'x', status: 'unsupported', similarity: 0.2, best_chunk_id: null, cited: [1], issues: [] }], supported_ratio: 0, flagged: 1, method: 'm', note: 'n' },
        }}
      />,
    )
    expect(screen.getByText('high blood pressure').tagName).toBe('STRONG')
    expect(screen.getByRole('link', { name: /Hypertension/ })).toHaveAttribute('href', 'https://www.who.int/x')
    expect(screen.getByText('World Health Organization')).toBeInTheDocument()
    expect(screen.getByText('Fact sheet')).toBeInTheDocument()
    expect(screen.getByText(/Updated .*2025/)).toBeInTheDocument()
    expect(screen.getByText('1 not found in sources')).toBeInTheDocument()
    expect(screen.getByText('Where this comes from (1)')).toBeInTheDocument()
    await userEvent.click(screen.getByText(/Read the part we used/))
    expect(screen.getByText(/How closely this matches your question: 71%/)).toBeInTheDocument()
  })

  it('does not present a missing answer as if it were one', async () => {
    const { MessageBubble } = await import('@/components/assistant/MessageBubble')
    render(<MessageBubble m={{ id: 2, role: 'assistant', content: 'I could not find a reliable answer.', created_at: '', retrieval_strategy: null, sources: [], verification: null, status: 'insufficient_evidence' }} />)
    expect(screen.getByText('No reliable answer found')).toBeInTheDocument()
  })

  it('labels quoted answers as word-for-word quotes', async () => {
    const { MessageBubble } = await import('@/components/assistant/MessageBubble')
    render(<MessageBubble m={{ id: 3, role: 'assistant', content: 'Here is what trusted health sources say, word for word:\n\n- Hypertension is high blood pressure. [1]', created_at: '', retrieval_strategy: 'adaptive', sources: [], verification: null, status: 'extractive' }} />)
    expect(screen.getByText('Taken word for word from trusted sources')).toBeInTheDocument()
  })
})

describe('Report upload validation', () => {
  it('accepts supported files and explains problems with others', async () => {
    const { validateFile } = await import('@/pages/Reports')
    const f = (name: string, type: string, size = 10) => new File([new Uint8Array(size)], name, { type })
    expect(validateFile(f('lab.pdf', 'application/pdf'))).toBeNull()
    expect(validateFile(f('scan.JPG', 'image/jpeg'))).toBeNull()
    expect(validateFile(f('notes.txt', 'text/plain'))).toBe('Please choose a PDF, JPG or PNG file.')
    expect(validateFile(f('lab.pdf', 'application/pdf', 0))).toMatch(/empty/)
    expect(validateFile(f('big.pdf', 'application/pdf', 11 * 1024 * 1024))).toMatch(/too big/)
  })
})

describe('Locator helpers', () => {
  it('formats distances', async () => {
    const { formatDistance } = await import('@/pages/Locator')
    expect(formatDistance(850)).toBe('850 m')
    expect(formatDistance(2340)).toBe('2.3 km')
    expect(formatDistance(15200)).toBe('15 km')
  })
})

describe('Settings', () => {
  it('keeps account deletion disabled until the password and "DELETE" are entered', async () => {
    mockApi()
    const { default: Settings } = await import('@/pages/Settings')
    withProviders(<Settings />, '/settings')
    const btn = await screen.findByRole('button', { name: /Delete my account/ })
    expect(btn).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Password', { selector: '#del_pw' }), 'Passw0rd!')
    expect(btn).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/Type "DELETE"/), 'DELETE')
    expect(btn).toBeEnabled()
  })
})

describe('Reminders', () => {
  it('validates the form in plain words before calling the API', async () => {
    mockApi()
    const post = vi.spyOn(api, 'post')
    const { default: Reminders } = await import('@/pages/Reminders')
    withProviders(<Reminders />, '/reminders')
    await userEvent.click(await screen.findByRole('button', { name: /Add reminder/ }))
    expect(await screen.findByText('Please enter the name of the medicine')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Medicine name'), 'Metformin')
    await userEvent.selectOptions(screen.getByLabelText('How often do you take it?'), 'weekly')
    await userEvent.click(screen.getByRole('button', { name: /Add reminder/ }))
    expect(await screen.findByText('Please choose at least one day')).toBeInTheDocument()
    expect(post).not.toHaveBeenCalled()
    post.mockResolvedValueOnce({ data: {} })
    await userEvent.click(screen.getByRole('button', { name: 'Mon' }))
    await userEvent.click(screen.getByRole('button', { name: /Add reminder/ }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/reminders', expect.objectContaining({ medication_name: 'Metformin', frequency: 'weekly', days_of_week: [0], times: ['08:00'] })))
  })
})

describe('ErrorBoundary', () => {
  it('shows a recoverable message instead of a blank page when a component crashes', async () => {
    const { ErrorBoundary } = await import('@/components/ErrorBoundary')
    const Boom = () => {
      throw new Error('kaboom')
    }
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong on this page')
    expect(screen.getByRole('button', { name: /Reload/ })).toBeInTheDocument()
  })
})

describe('Ask a Question page', () => {
  it('renders, offers example questions, and keeps jargon out', async () => {
    mockApi()
    const { default: Assistant } = await import('@/pages/Assistant')
    withProviders(<Assistant />, '/assistant')
    expect(await screen.findByLabelText('Your question')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /What is the difference between HDL and LDL/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Ask a Health Question' })).toBeInTheDocument()
    expectNoJargon()
  })

  it('pre-fills a question sent from another page', async () => {
    mockApi()
    const { default: Assistant } = await import('@/pages/Assistant')
    withProviders(<Assistant />, '/assistant?q=What%20is%20prediabetes%3F')
    expect(await screen.findByLabelText('Your question')).toHaveValue('What is prediabetes?')
  })
})

describe('Navigation and pages for everyday users', () => {
  it('uses plain names in the menu, in groups, with the technical pages tucked under "How it works"', async () => {
    localStorage.setItem(TOKEN_KEY, 'tok')
    mockApi()
    withProviders(
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<p>home</p>} />
        </Route>
      </Routes>,
      '/dashboard',
    )
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    const labels = within(nav).getAllByRole('link').map((a) => a.textContent)
    expect(labels).toEqual(['Home', 'Ask a Question', 'My Lab Results', 'Health Check', 'Find Care Nearby', 'Medicine Reminders', 'How it works', 'Help & safety', 'Settings & privacy'])
    expect(screen.getByText(/It is not a doctor and cannot diagnose you/)).toBeInTheDocument()
  })

  it('Home greets the user by name and lists what they can do', async () => {
    mockApi()
    const { default: Dashboard } = await import('@/pages/Dashboard')
    withProviders(<Dashboard />, '/dashboard')
    expect(await screen.findByRole('heading', { name: 'Hello, Sam' })).toBeInTheDocument()
    for (const t of ['Ask a health question', 'Understand my lab results', 'Do a 2-minute health check', 'Find care near me', 'Medicine reminders']) {
      expect(screen.getByRole('heading', { name: t })).toBeInTheDocument()
    }
    expectNoJargon()
  })

  it('Help lists emergency numbers and answers common questions', async () => {
    const { default: Help } = await import('@/pages/Help')
    withProviders(<Help />, '/help')
    expect(screen.getByText(/In an emergency, call your local emergency number/)).toBeInTheDocument()
    expect(screen.getByText('911')).toBeInTheDocument()
    expect(screen.getByText('Is MediCore a doctor?')).toBeInTheDocument()
    expect(screen.getByText('I forgot my password')).toBeInTheDocument()
  })

  it('Privacy and Terms are readable and never show invented company details', async () => {
    const { Privacy, Terms } = await import('@/pages/Legal')
    const { unmount } = withProviders(<Privacy />, '/privacy')
    expect(screen.getByText(/We do not keep the lab report files you upload/)).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/\[.*\]|lorem|TODO|example\.com/i)
    unmount()
    withProviders(<Terms />, '/terms')
    expect(screen.getByText(/It is not for emergencies/)).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/\[.*\]|lorem|TODO|example\.com/i)
  })
})

describe('Answers with limited evidence', () => {
  it('say so clearly, and still show where the information came from', async () => {
    const { MessageBubble } = await import('@/components/assistant/MessageBubble')
    render(
      <MessageBubble
        m={{
          id: 9, role: 'assistant', content: 'The sources I found only partly match your question.\n\n**Short answer**\n- Fatigue is feeling very tired. [1]', created_at: '',
          retrieval_strategy: 'hybrid', verification: null, status: 'limited_evidence', notes: ['The sources only partly match your question, so this is general information and may be incomplete.'],
          sources: [{ rank: 1, chunk_id: 'm#0', doc_id: 'm', title: 'MedlinePlus: Fatigue', source: 'MedlinePlus', doc_type: 'health_topic', url: 'https://medlineplus.gov/fatigue.html', published: '2026-11-12', snippet: 's', relevance: 0.5, score_breakdown: { similarity: 0.5, source_reliability: 1, recency: 1, clinical_relevance: 0.5 } }],
        }}
      />,
    )
    expect(screen.getByText('Limited evidence: general information only')).toBeInTheDocument()
    expect(screen.getByText('Short answer')).toBeInTheDocument()
    expect(screen.getByText('Where this comes from (1)')).toBeInTheDocument()
    expect(screen.getByText('MedlinePlus')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Fatigue/ })).toHaveAttribute('href', 'https://medlineplus.gov/fatigue.html')
  })
})
