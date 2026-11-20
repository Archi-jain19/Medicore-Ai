import { useState } from 'react'
import { Link, Outlet } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { Logo } from '@/components/Logo'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { AppLayout } from './AppLayout'

const NAV = [
  { href: '/#features', label: 'What you can do' },
  { href: '/#how', label: 'How it works' },
  { href: '/#safety', label: 'Safety' },
  { href: '/help', label: 'Help' },
]

export function PublicLayout() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-card focus:px-3 focus:py-2">
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b bg-card/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
          <Logo />
          <nav aria-label="Main" className="hidden items-center gap-7 text-sm text-muted-foreground md:flex">
            {NAV.map((n) => (
              <a key={n.href} href={n.href} className="hover:text-foreground">
                {n.label}
              </a>
            ))}
          </nav>
          <div className="hidden items-center gap-2 md:flex">
            {user ? (
              <Button asChild>
                <Link to="/dashboard">Go to my home page</Link>
              </Button>
            ) : (
              <>
                <Button variant="ghost" asChild>
                  <Link to="/login">Sign in</Link>
                </Button>
                <Button asChild>
                  <Link to="/register">Get started free</Link>
                </Button>
              </>
            )}
          </div>
          <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open or close the menu" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? <X /> : <Menu />}
          </Button>
        </div>
        {open && (
          <div className="border-t bg-card px-4 py-3 md:hidden">
            <nav aria-label="Mobile" className="grid gap-1">
              {NAV.map((n) => (
                <a key={n.href} href={n.href} onClick={() => setOpen(false)} className="rounded-md px-2 py-2.5 text-[15px] hover:bg-secondary">
                  {n.label}
                </a>
              ))}
            </nav>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {user ? (
                <Button asChild className="col-span-2">
                  <Link to="/dashboard">Go to my home page</Link>
                </Button>
              ) : (
                <>
                  <Button variant="outline" asChild>
                    <Link to="/login">Sign in</Link>
                  </Button>
                  <Button asChild>
                    <Link to="/register">Get started</Link>
                  </Button>
                </>
              )}
            </div>
          </div>
        )}
      </header>
      <main id="main" className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t bg-card">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 text-sm text-muted-foreground md:grid-cols-[1.2fr_1fr_1fr]">
          <div className="space-y-2">
            <Logo />
            <p>Health information in plain words, with the sources shown.</p>
          </div>
          <div className="space-y-1.5">
            <p className="font-medium text-foreground">Please remember</p>
            <p>
              MediCore is not a doctor. It cannot diagnose you or prescribe medicine. In an emergency, call your local emergency number.
            </p>
          </div>
          <div className="space-y-1.5">
            <p className="font-medium text-foreground">More</p>
            <ul className="space-y-1">
              <li>
                <Link className="hover:text-foreground hover:underline" to="/learn">
                  How it works
                </Link>
              </li>
              <li>
                <Link className="hover:text-foreground hover:underline" to="/help">
                  Help and safety
                </Link>
              </li>
              <li>
                <Link className="hover:text-foreground hover:underline" to="/privacy">
                  Privacy policy
                </Link>
              </li>
              <li>
                <Link className="hover:text-foreground hover:underline" to="/terms">
                  Terms of use
                </Link>
              </li>
            </ul>
          </div>
        </div>
      </footer>
    </div>
  )
}

/** Pages anyone can read (Help, How it works, Privacy, Terms). Signed-in people keep their normal menu. */
export function AdaptiveLayout() {
  const { user, loading } = useAuth()
  if (loading) return null
  return user ? <AppLayout /> : <PublicLayout />
}
