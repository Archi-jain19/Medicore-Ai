import { useCallback, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertCircle, ChevronDown, Download, ExternalLink, FileText, FileUp, Info, ShieldCheck, Trash2 } from 'lucide-react'
import { EmptyState, ErrorState, PageHeader } from '@/components/common'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton, Spinner, Table, TBody, TD, TH, THead, TR } from '@/components/ui/misc'
import { useApi } from '@/hooks/useApi'
import { cn } from '@/lib/utils'
import { api, errorMessage } from '@/services/api'
import type { LabFlag, LabResult, ReportDetail, ReportListItem } from '@/types/api'
import { dateTime } from '@/utils/format'

const MAX_MB = 10
const ACCEPT: Record<string, string> = { 'application/pdf': '.pdf', 'image/png': '.png', 'image/jpeg': '.jpg' }

const FLAG_META: Record<LabFlag, { label: string; variant: 'success' | 'warning' | 'destructive' | 'outline' }> = {
  normal: { label: 'In the normal range', variant: 'success' },
  high: { label: 'Higher than normal', variant: 'destructive' },
  low: { label: 'Lower than normal', variant: 'warning' },
  unknown: { label: 'No range to check', variant: 'outline' },
}

/** Client-side checks mirror the server's; the server re-validates by file signature. */
// eslint-disable-next-line react-refresh/only-export-components
export function validateFile(f: File): string | null {
  const ext = f.name.toLowerCase().split('.').pop() ?? ''
  if (!['pdf', 'png', 'jpg', 'jpeg'].includes(ext)) return 'Please choose a PDF, JPG or PNG file.'
  if (f.type && !(f.type in ACCEPT)) return 'Please choose a PDF, JPG or PNG file.'
  if (f.size === 0) return 'That file is empty.'
  if (f.size > MAX_MB * 1024 * 1024) return `That file is too big (the limit is ${MAX_MB} MB).`
  return null
}

function Dropzone({ onFile, busy }: { onFile: (f: File) => void; busy: boolean }) {
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        const f = e.dataTransfer.files[0]
        if (f && !busy) onFile(f)
      }}
      className={cn(
        'flex flex-col items-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors',
        over ? 'border-teal bg-accent/40' : 'border-border bg-card',
      )}
    >
      <span className="grid size-12 place-items-center rounded-full bg-accent text-accent-foreground">
        {busy ? <Spinner className="size-5" /> : <FileUp className="size-5" />}
      </span>
      <div>
        <p className="font-medium">{busy ? 'Reading your report…' : 'Drag and drop your lab report here'}</p>
        <p className="text-sm text-muted-foreground">PDF, JPG or PNG · up to {MAX_MB} MB · photos and scans work too</p>
      </div>
      <Button type="button" variant="outline" disabled={busy} onClick={() => input.current?.click()}>
        Choose a file
      </Button>
      <input
        ref={input}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
        className="sr-only"
        aria-label="Upload lab report"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onFile(f)
          e.target.value = ''
        }}
      />
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <ShieldCheck className="size-3.5 text-teal" /> Your file is read once and not kept. We only save the results, and you can delete them any
        time.
      </p>
    </div>
  )
}

function ResultRow({ r }: { r: LabResult }) {
  const [open, setOpen] = useState(false)
  const meta = FLAG_META[r.flag]
  const e = r.explanation
  return (
    <>
      <TR className={cn('cursor-pointer', open && 'bg-muted/40')} onClick={() => setOpen(!open)}>
        <TD className="font-medium">
          <span className="flex items-center gap-1.5">
            <ChevronDown className={cn('size-3.5 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
            {r.parameter}
          </span>
          {r.printed_name && r.printed_name !== r.parameter && <span className="block pl-5 text-xs text-muted-foreground">written on your report as: {r.printed_name}</span>}
        </TD>
        <TD className={cn('tabular-nums', (r.flag === 'high' || r.flag === 'low') && 'font-semibold')}>{r.value_text}</TD>
        <TD>{r.unit ?? '—'}</TD>
        <TD className="tabular-nums">{r.ref_text ?? <span className="text-muted-foreground">not shown</span>}</TD>
        <TD>
          <Badge variant={meta.variant}>{r.flag_source === 'lab_flag' ? `Marked ${r.flag} by the lab` : meta.label}</Badge>
        </TD>
      </TR>
      {open && (
        <TR className="bg-muted/20 hover:bg-muted/20">
          <TD colSpan={5}>
            <div className="space-y-1.5 py-1 text-sm">
              {e.what_it_measures && <p>{e.what_it_measures}</p>}
              <p className="font-medium">{e.status}</p>
              {e.context && <p className="text-muted-foreground">{e.context}</p>}
              {e.learn_more && (
                <a href={e.learn_more.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
                  Learn more: {e.learn_more.title} ({e.learn_more.source}
                  {e.learn_more.published ? `, ${e.learn_more.published}` : ''}) <ExternalLink className="size-3" />
                </a>
              )}
            </div>
          </TD>
        </TR>
      )}
    </>
  )
}

function ReportView({ report, onDeleted }: { report: ReportDetail; onDeleted: () => void }) {
  const [busy, setBusy] = useState<'download' | 'delete' | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const download = async () => {
    setBusy('download')
    setErr(null)
    try {
      const { data } = await api.get<Blob>(`/reports/${report.id}/summary.pdf`, { responseType: 'blob' })
      const url = URL.createObjectURL(data)
      const a = document.createElement('a')
      a.href = url
      a.download = `medicore-summary-${report.id}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }
  const remove = async () => {
    if (!window.confirm('Delete this report and its results? This cannot be undone.')) return
    setBusy('delete')
    try {
      await api.delete(`/reports/${report.id}`)
      onDeleted()
    } catch (e) {
      setErr(errorMessage(e))
      setBusy(null)
    }
  }
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-1">
            <CardTitle className="truncate">{report.original_filename}</CardTitle>
            <p className="text-xs text-muted-foreground">
              Read on {dateTime(report.created_at)} · {report.extraction_method === 'ocr' ? 'from a photo or scan' : 'from a PDF'} ·{' '}
              {report.page_count ?? 1} {(report.page_count ?? 1) === 1 ? 'page' : 'pages'}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={download} disabled={!!busy || report.results.length === 0}>
              {busy === 'download' ? <Spinner /> : <Download />} Download summary
            </Button>
            <Button variant="outline" size="sm" onClick={remove} disabled={!!busy} aria-label="Delete report">
              {busy === 'delete' ? <Spinner /> : <Trash2 />} Delete
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {err && (
          <Alert variant="destructive">
            <AlertCircle />
            <span>{err}</span>
          </Alert>
        )}
        <p className="text-sm leading-relaxed">{report.summary}</p>
        {report.results.length > 0 ? (
          <Table>
            <THead>
              <TR>
                <TH>Test</TH>
                <TH>Your result</TH>
                <TH>Unit</TH>
                <TH>Normal range on your report</TH>
                <TH>Compared with range</TH>
              </TR>
            </THead>
            <TBody>
              {report.results.map((r) => (
                <ResultRow key={r.id} r={r} />
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState
            icon={FileText}
            title="We could not find any lab results"
            body="We look for a test name, a number, and ideally a unit and normal range on each line. Try a clearer photo, or a PDF where you can select the text."
          />
        )}
        <Alert variant="warning">
          <Info />
          <span className="text-sm">{report.disclaimer}</span>
        </Alert>
      </CardContent>
    </Card>
  )
}

export default function Reports() {
  const [params, setParams] = useSearchParams()
  const activeId = params.get('r')
  const [tick, setTick] = useState(0)
  const list = useApi<ReportListItem[]>(`/reports?t=${tick}`)
  const detail = useApi<ReportDetail>(activeId ? `/reports/${activeId}?t=${tick}` : null)
  const [busy, setBusy] = useState(false)
  const [uploadErr, setUploadErr] = useState<string | null>(null)

  const onFile = useCallback(
    async (f: File) => {
      setUploadErr(null)
      const problem = validateFile(f)
      if (problem) {
        setUploadErr(problem)
        return
      }
      setBusy(true)
      try {
        const form = new FormData()
        form.append('file', f)
        const { data } = await api.post<ReportDetail>('/reports/upload', form)
        setParams({ r: String(data.id) })
        setTick((t) => t + 1)
      } catch (e) {
        setUploadErr(errorMessage(e))
      } finally {
        setBusy(false)
      }
    },
    [setParams],
  )

  return (
    <>
      <PageHeader
        title="My Lab Results"
        description="Upload a lab report (a PDF or a photo) and we will explain each test in plain words. We compare each result only with the normal range printed on your own report."
      />
      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <div className="space-y-4">
          <Dropzone onFile={onFile} busy={busy} />
          {uploadErr && (
            <Alert variant="destructive">
              <AlertCircle />
              <span>{uploadErr}</span>
            </Alert>
          )}
          {activeId &&
            (detail.error ? (
              <ErrorState message={detail.error} onRetry={detail.reload} />
            ) : !detail.data ? (
              <Skeleton className="h-64 rounded-xl" />
            ) : (
              <ReportView
                report={detail.data}
                onDeleted={() => {
                  setParams({})
                  setTick((t) => t + 1)
                }}
              />
            ))}
        </div>
        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Your earlier reports</CardTitle>
          </CardHeader>
          <CardContent>
            {list.error ? (
              <ErrorState message={list.error} onRetry={list.reload} />
            ) : !list.data ? (
              <Skeleton className="h-20" />
            ) : list.data.length === 0 ? (
              <p className="text-sm text-muted-foreground">No reports yet. Upload one to get started.</p>
            ) : (
              <ul className="space-y-1">
                {list.data.map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      onClick={() => setParams({ r: String(r.id) })}
                      className={cn('w-full rounded-md px-2 py-2 text-left hover:bg-secondary', String(r.id) === activeId && 'bg-accent')}
                    >
                      <p className="truncate text-sm font-medium">{r.original_filename}</p>
                      <p className="text-xs text-muted-foreground">
                        {dateTime(r.created_at)} · {r.result_count} results
                        {r.flagged_count > 0 && <span className="text-destructive"> · {r.flagged_count} outside the normal range</span>}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  )
}
