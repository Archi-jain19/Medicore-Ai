import type { ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'

export function ContentPage({ title, intro, children }: { title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <article className="mx-auto w-full max-w-3xl px-4 py-10 sm:py-14">
      <h1 className="text-3xl font-semibold text-primary">{title}</h1>
      {intro && <p className="mt-3 text-lg text-muted-foreground">{intro}</p>}
      <div className="mt-8 space-y-10 text-[15px] leading-relaxed">{children}</div>
    </article>
  )
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-primary">{title}</h2>
      <div className="space-y-3 [&_a]:text-primary [&_a]:underline [&_li]:mt-1.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:pl-5">{children}</div>
    </section>
  )
}

export function Faq({ q, children }: { q: string; children: ReactNode }) {
  return (
    <details className="group rounded-xl border bg-card px-4 py-3 open:shadow-sm">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-medium">
        {q}
        <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-3 space-y-2 text-muted-foreground [&_a]:text-primary [&_a]:underline [&_li]:mt-1 [&_ul]:list-disc [&_ul]:pl-5">{children}</div>
    </details>
  )
}

/** Optional operator details, set at build time. Nothing is shown (and nothing is invented) when unset. */
// eslint-disable-next-line react-refresh/only-export-components
export const OPERATOR = {
  name: (import.meta.env.VITE_OPERATOR_NAME as string | undefined)?.trim() || null,
  email: (import.meta.env.VITE_SUPPORT_EMAIL as string | undefined)?.trim() || null,
}
