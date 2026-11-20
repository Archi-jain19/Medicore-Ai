import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertCircle, MessageSquarePlus, Send, Trash2 } from 'lucide-react'
import { MessageBubble } from '@/components/assistant/MessageBubble'
import { ErrorState, PageHeader } from '@/components/common'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { useApi } from '@/hooks/useApi'
import { cn } from '@/lib/utils'
import { api, errorMessage } from '@/services/api'
import type { ChatMessage, ChatResponse, Conversation, ConversationDetail, RagStatus } from '@/types/api'
import { shortDate } from '@/utils/format'

const SUGGESTED = [
  'Why do I have a headache?',
  'What is a fever?',
  'What is dehydration?',
  'What does haemoglobin mean?',
  'What is the difference between HDL and LDL?',
  'I am feeling cold.',
]

function TypingIndicator() {
  return (
    <div className="flex w-fit items-center gap-1 rounded-2xl rounded-bl-sm border bg-card px-4 py-3" role="status" aria-label="Assistant is typing">
      {[0, 150, 300].map((d) => (
        <span key={d} className="size-1.5 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: `${d}ms` }} />
      ))}
      <span className="ml-2 text-xs text-muted-foreground">Looking through trusted sources…</span>
    </div>
  )
}

export default function Assistant() {
  const [params, setParams] = useSearchParams()
  const activeId = params.get('c') ? Number(params.get('c')) : null
  const status = useApi<RagStatus>('/rag/status')
  const [listTick, setListTick] = useState(0)
  const convs = useApi<Conversation[]>(`/chat/history?t=${listTick}`)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loadingConv, setLoadingConv] = useState(false)
  const [input, setInput] = useState(params.get('q') ?? '')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const skipLoad = useRef(false)

  useEffect(() => {
    if (skipLoad.current) {
      skipLoad.current = false
      return
    }
    if (!activeId) {
      setMessages([])
      return
    }
    setLoadingConv(true)
    api
      .get<ConversationDetail>(`/chat/${activeId}`)
      .then((r) => setMessages(r.data.messages))
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoadingConv(false))
  }, [activeId])

  useEffect(() => {
    // braces matter: an effect must not return scrollIntoView's result (Chrome returns a Promise there)
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, sending])

  const send = async (text: string) => {
    const msg = text.trim()
    if (msg.length < 2 || sending) return
    setError(null)
    setSending(true)
    setInput('')
    const optimistic: ChatMessage = { id: -Date.now(), role: 'user', content: msg, sources: null, verification: null, retrieval_strategy: null, created_at: new Date().toISOString() }
    setMessages((m) => [...m, optimistic])
    try {
      const { data } = await api.post<ChatResponse>('/chat', { message: msg, conversation_id: activeId })
      const reply: ChatMessage = { ...data.reply, status: data.status, emergency_notice: data.emergency_notice, notes: data.notes, analysis: data.analysis }
      setMessages((m) => [...m.filter((x) => x.id !== optimistic.id), data.user_message, reply])
      if (data.conversation_id !== activeId) {
        skipLoad.current = true
        setParams({ c: String(data.conversation_id) })
      }
      setListTick((t) => t + 1)
    } catch (e) {
      setMessages((m) => m.filter((x) => x.id !== optimistic.id))
      setInput(msg)
      setError(errorMessage(e))
    } finally {
      setSending(false)
    }
  }

  const newChat = () => {
    setParams({})
    setMessages([])
    setError(null)
  }

  const remove = async (id: number) => {
    if (!window.confirm('Delete this question and its answer? This cannot be undone.')) return
    try {
      await api.delete(`/chat/${id}`)
      if (id === activeId) newChat()
      setListTick((t) => t + 1)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const st = status.data
  return (
    <>
      <PageHeader
        title="Ask a Health Question"
        description="Ask about a condition, a medical word or a lab test. Answers come from trusted sources (the World Health Organization, the US CDC and PubMed) and show where each fact came from."
        actions={
          <Button variant="outline" onClick={newChat}>
            <MessageSquarePlus /> New question
          </Button>
        }
      />
      {st && !st.knowledge_base_built && (
        <Alert variant="warning" className="mb-4">
          <AlertCircle />
          <span className="text-sm">Our health library is not available right now. Please try again later.</span>
        </Alert>
      )}
      

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <Card className="h-fit lg:sticky lg:top-6">
          <CardContent className="p-3">
            <p className="px-2 pb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Your earlier questions</p>
            {convs.error ? (
              <ErrorState message={convs.error} onRetry={convs.reload} />
            ) : !convs.data ? (
              <div className="space-y-2">
                <Skeleton className="h-8" />
                <Skeleton className="h-8" />
              </div>
            ) : convs.data.length === 0 ? (
              <p className="px-2 py-3 text-sm text-muted-foreground">Nothing yet. Your questions will be saved here.</p>
            ) : (
              <ul className="max-h-[50vh] space-y-1 overflow-y-auto">
                {convs.data.map((c) => (
                  <li key={c.id} className={cn('group flex items-center gap-1 rounded-md', c.id === activeId ? 'bg-accent' : 'hover:bg-secondary')}>
                    <button type="button" onClick={() => setParams({ c: String(c.id) })} className="min-w-0 flex-1 px-2 py-2 text-left">
                      <p className="truncate text-sm">{c.title}</p>
                      <p className="text-[11px] text-muted-foreground">
                        {shortDate(c.updated_at)} · {c.message_count / 2} {c.message_count / 2 === 1 ? 'question' : 'questions'}
                      </p>
                    </button>
                    <Button variant="ghost" size="icon" aria-label={`Delete question: ${c.title}`} className="size-7 opacity-60 group-hover:opacity-100" onClick={() => remove(c.id)}>
                      <Trash2 className="size-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="flex min-h-[65vh] flex-col">
          <div className="flex-1 space-y-6 overflow-y-auto p-4 sm:p-6">
            {loadingConv ? (
              <div className="space-y-3">
                <Skeleton className="ml-auto h-10 w-2/3" />
                <Skeleton className="h-32 w-full" />
              </div>
            ) : messages.length === 0 && !sending ? (
              <div className="mx-auto max-w-xl space-y-4 py-8 text-center">
                <h2 className="text-lg font-semibold text-primary">What would you like to know?</h2>
                <p className="text-sm text-muted-foreground">
                  Type your question in your own words, or tap one below. If our sources do not cover it, we will tell you instead of guessing.
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {SUGGESTED.map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => send(q)}
                      className="rounded-lg border bg-card px-3 py-2 text-left text-sm transition-colors hover:border-teal hover:bg-accent/40"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => <MessageBubble key={m.id} m={m} />)
            )}
            {sending && <TypingIndicator />}
            <div ref={bottom} />
          </div>
          <div className="border-t p-3 sm:p-4">
            {error && (
              <Alert variant="destructive" className="mb-3">
                <AlertCircle />
                <span>{error}</span>
              </Alert>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault()
                void send(input)
              }}
              className="flex items-end gap-2"
            >
              <label htmlFor="chat-input" className="sr-only">
                Your question
              </label>
              <textarea
                id="chat-input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    void send(input)
                  }
                }}
                rows={2}
                maxLength={2000}
                placeholder="Type your question here…"
                className="min-h-[44px] flex-1 resize-none rounded-md border border-input bg-card px-3 py-2 text-sm shadow-xs focus-visible:border-ring focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40"
              />
              <Button type="submit" size="icon" className="size-11" disabled={sending || input.trim().length < 2} aria-label="Send">
                <Send />
              </Button>
            </form>
            <p className="mt-2 text-[11px] text-muted-foreground">
              For information only. This is not medical advice. In an emergency, call your local emergency number.
            </p>
          </div>
        </Card>
      </div>
    </>
  )
}
