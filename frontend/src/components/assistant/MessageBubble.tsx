import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AlertTriangle, BookOpen, ChevronDown, ExternalLink, ShieldAlert, ShieldCheck, Siren } from 'lucide-react'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { ChatMessage, SourceDoc, Verification } from '@/types/api'
import { pct } from '@/utils/format'

const SOURCE_TONE: Record<string, string> = {
  WHO: 'bg-sky/15 text-[oklch(0.45_0.12_235)]',
  CDC: 'bg-accent text-accent-foreground',
  PubMed: 'bg-primary/10 text-primary',
}
const SOURCE_NAME: Record<string, string> = { WHO: 'World Health Organization', CDC: 'US CDC', PubMed: 'PubMed research' }
const TYPE_NAME: Record<string, string> = {
  fact_sheet: 'Fact sheet',
  web_page: 'Health article',
  guideline: 'Medical guideline',
  review: 'Research review',
  systematic_review: 'Research review',
  article: 'Research article',
}

/** "2025-09-25" -> "Sep 2025" */
// eslint-disable-next-line react-refresh/only-export-components
export function friendlyMonth(iso: string | null) {
  if (!iso) return 'Date not shown'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? 'Date not shown' : `Updated ${d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}`
}

function SourceCard({ s }: { s: SourceDoc }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="rounded-lg border bg-card p-3 text-sm">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded bg-secondary text-[11px] font-semibold" aria-label={`Source ${s.rank}`}>
          {s.rank}
        </span>
        <div className="min-w-0 flex-1 space-y-1.5">
          <a href={s.url} target="_blank" rel="noreferrer" className="flex items-start gap-1 font-medium text-primary hover:underline">
            <span className="line-clamp-2">{s.title.replace(/^(WHO fact sheet|CDC): /, '')}</span>
            <ExternalLink className="mt-0.5 size-3 shrink-0" aria-label="opens in a new tab" />
          </a>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span className={cn('rounded px-1.5 py-0.5 font-medium', SOURCE_TONE[s.source] ?? 'bg-secondary')}>{SOURCE_NAME[s.source] ?? s.source}</span>
            <span>{TYPE_NAME[s.doc_type] ?? 'Source'}</span>
            <span>{friendlyMonth(s.published)}</span>
          </div>
          <button type="button" onClick={() => setOpen(!open)} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground" aria-expanded={open}>
            <ChevronDown className={cn('size-3 transition-transform', open && 'rotate-180')} /> {open ? 'Hide' : 'Read'} the part we used
          </button>
          {open && (
            <div className="space-y-1.5 pt-1">
              <p className="whitespace-pre-line rounded-md bg-secondary/60 p-2 text-xs leading-relaxed">{s.snippet}</p>
              <p className="text-[11px] text-muted-foreground">How closely this matches your question: {pct(s.relevance, 0)}</p>
            </div>
          )}
        </div>
      </div>
    </li>
  )
}

const CLAIM_LABEL = { supported: 'Matches', weak: 'Partly matches', unsupported: 'Not found in sources' } as const

function VerificationPanel({ v }: { v: Verification }) {
  const [open, setOpen] = useState(false)
  if (!v.claims.length) return null
  const total = v.claims.length
  const ok = v.claims.filter((c) => c.status === 'supported').length
  const allGood = v.flagged === 0 && ok === total
  return (
    <div className="rounded-lg border p-3 text-xs">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between gap-2 text-left">
        <span className="flex flex-wrap items-center gap-2 font-medium">
          {v.flagged === 0 ? <ShieldCheck className="size-4 text-success" /> : <ShieldAlert className="size-4 text-destructive" />}
          Fact check: {allGood ? `all ${total} statements match the sources` : `${ok} of ${total} statements match the sources`}
          {v.flagged > 0 && <Badge variant="destructive">{v.flagged} not found in sources</Badge>}
        </span>
        <ChevronDown className={cn('size-3 shrink-0 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <ul className="mt-2 space-y-1.5">
          {v.claims.map((c, i) => (
            <li key={i} className="flex gap-2">
              <Badge variant={c.status === 'supported' ? 'success' : c.status === 'weak' ? 'warning' : 'destructive'} className="h-fit shrink-0">
                {CLAIM_LABEL[c.status]}
              </Badge>
              <span className="text-muted-foreground">
                {c.text}
                {c.issues.length > 0 && <span className="block text-destructive/80">{c.issues.join('; ')}</span>}
              </span>
            </li>
          ))}
          <li className="pt-1 text-muted-foreground">{v.note}</li>
        </ul>
      )}
    </div>
  )
}

export function MessageBubble({ m }: { m: ChatMessage }) {
  if (m.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-[15px] text-primary-foreground">{m.content}</div>
      </div>
    )
  }
  const sources = m.sources ?? []
  const status = m.status
  const notice =
    status === 'insufficient_evidence'
      ? 'No reliable answer found'
      : status === 'limited_evidence'
        ? 'Limited evidence: general information only'
        : status === 'generation_unavailable'
          ? 'No clear answer found'
          : status === 'knowledge_base_missing'
            ? 'Health library unavailable'
            : null
  return (
    <div className="space-y-3">
      {m.emergency_notice && (
        <Alert variant="destructive">
          <Siren />
          <ReactMarkdown>{m.emergency_notice}</ReactMarkdown>
        </Alert>
      )}
      <div className="rounded-2xl rounded-bl-sm border bg-card px-4 py-3 shadow-xs">
        {status === 'extractive' && (
          <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-accent-foreground">
            <BookOpen className="size-3.5" /> Taken word for word from trusted sources
          </p>
        )}
        {notice && (
          <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-[oklch(0.5_0.12_70)]">
            <AlertTriangle className="size-3.5" />
            {notice}
          </p>
        )}
        <div className="prose-chat text-[15px] leading-relaxed">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: (p) => <a {...p} target="_blank" rel="noreferrer" /> }}>
            {m.content || '_No answer was found._'}
          </ReactMarkdown>
        </div>
        {m.notes && m.notes.length > 0 && (
          <ul className="mt-2 space-y-0.5 border-t pt-2 text-xs text-muted-foreground">
            {m.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        )}
      </div>
      {m.verification && <VerificationPanel v={m.verification} />}
      {sources.length > 0 && (
        <div className="space-y-2">
          <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <BookOpen className="size-3.5" /> {status === 'ok' || status === 'extractive' || status === 'limited_evidence' || m.verification ? 'Where this comes from' : 'Related sources'} ({sources.length})
          </p>
          <ol className="grid gap-2 lg:grid-cols-2">
            {sources.map((s) => (
              <SourceCard key={s.chunk_id} s={s} />
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}
