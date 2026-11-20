import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'

const RELOAD_KEY = 'medicore.chunk-reload'

function isChunkLoadError(e: Error) {
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(e.message)
}

/** Catches render errors so a single broken component never blanks the whole app. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // After a deploy, old lazy chunks disappear: reload once to fetch the new build.
    if (isChunkLoadError(error)) {
      try {
        if (!sessionStorage.getItem(RELOAD_KEY)) {
          sessionStorage.setItem(RELOAD_KEY, '1')
          window.location.reload()
          return
        }
      } catch {
        /* storage unavailable */
      }
    }
    console.error('UI error', error, info.componentStack)
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div role="alert" className="mx-auto my-16 max-w-md space-y-4 rounded-xl border bg-card p-6 text-center shadow-sm">
        <span className="mx-auto grid size-11 place-items-center rounded-full bg-destructive/10 text-destructive">
          <AlertTriangle className="size-5" />
        </span>
        <h2 className="text-lg font-semibold text-primary">Something went wrong on this page</h2>
        <p className="text-sm text-muted-foreground">Your data is safe. Try again, or go back to the dashboard.</p>
        <div className="flex justify-center gap-2">
          <Button
            onClick={() => {
              try {
                sessionStorage.removeItem(RELOAD_KEY)
              } catch {
                /* ignore */
              }
              window.location.reload()
            }}
          >
            <RefreshCw /> Reload
          </Button>
          <Button variant="outline" onClick={() => (window.location.href = '/dashboard')}>
            Dashboard
          </Button>
        </div>
      </div>
    )
  }
}
