import { Suspense, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  BellRing,
  FileText,
  HeartPulse,
  HelpCircle,
  Home,
  Lightbulb,
  LogOut,
  MapPin,
  Menu,
  MessageSquareText,
  Settings,
  ShieldAlert,
  X,
  type LucideIcon,
} from 'lucide-react'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { Logo } from '@/components/Logo'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/misc'
import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

/** Everyday tasks, in plain words. */
// eslint-disable-next-line react-refresh/only-export-components
export const MAIN_NAV: NavItem[] = [
  { to: '/dashboard', label: 'Home', icon: Home },
  { to: '/assistant', label: 'Ask a Question', icon: MessageSquareText, end: true },
  { to: '/reports', label: 'My Lab Results', icon: FileText },
  { to: '/analytics', label: 'Health Check', icon: HeartPulse },
  { to: '/locator', label: 'Find Care Nearby', icon: MapPin },
  { to: '/reminders', label: 'Medicine Reminders', icon: BellRing },
]
// eslint-disable-next-line react-refresh/only-export-components
export const MORE_NAV: NavItem[] = [
  { to: '/learn', label: 'How it works', icon: Lightbulb },
  { to: '/help', label: 'Help & safety', icon: HelpCircle },
  { to: '/settings', label: 'Settings & privacy', icon: Settings },
]

function NavGroup({ title, items, onNavigate }: { title?: string; items: NavItem[]; onNavigate?: () => void }) {
  return (
    <div className="grid gap-1">
      {title && <p className="px-3 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>}
      {items.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground',
              isActive && 'bg-accent text-accent-foreground hover:bg-accent',
            )
          }
        >
          <Icon className="size-[18px]" />
          {label}
        </NavLink>
      ))}
    </div>
  )
}

function SideNav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Main">
      <NavGroup items={MAIN_NAV} onNavigate={onNavigate} />
      <NavGroup title="More" items={MORE_NAV} onNavigate={onNavigate} />
    </nav>
  )
}

export function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const doLogout = () => {
    logout()
    navigate('/login')
  }
  const initials = (user?.full_name || user?.email || '?').slice(0, 1).toUpperCase()

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col overflow-y-auto border-r bg-sidebar p-4 lg:flex">
        <Logo to="/dashboard" className="mb-4 px-2" />
        <SideNav />
        <div className="mt-auto space-y-3 pt-4">
          <div className="flex items-center gap-3 rounded-lg border p-2.5">
            <span className="grid size-8 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              {initials}
            </span>
            <div className="min-w-0 text-xs">
              <p className="truncate font-medium">{user?.full_name || 'Your account'}</p>
              <p className="truncate text-muted-foreground">{user?.email}</p>
            </div>
          </div>
          <Button variant="outline" className="w-full" onClick={doLogout}>
            <LogOut /> Sign out
          </Button>
        </div>
      </aside>

      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-foreground/30" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 flex-col overflow-y-auto bg-card p-4 shadow-xl">
            <div className="mb-2 flex items-center justify-between px-2">
              <Logo to="/dashboard" />
              <Button variant="ghost" size="icon" aria-label="Close menu" onClick={() => setOpen(false)}>
                <X />
              </Button>
            </div>
            <SideNav onNavigate={() => setOpen(false)} />
            <Button variant="outline" className="mt-auto" onClick={doLogout}>
              <LogOut /> Sign out
            </Button>
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-card/90 px-4 backdrop-blur lg:hidden">
          <Button variant="ghost" size="icon" aria-label="Open menu" onClick={() => setOpen(true)}>
            <Menu />
          </Button>
          <Logo to="/dashboard" />
        </header>
        <div className="flex items-start gap-2 border-b bg-warning/10 px-4 py-2 text-xs text-foreground/80 sm:items-center">
          <ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-[oklch(0.55_0.13_70)] sm:mt-0" />
          <span>
            MediCore gives health information. It is not a doctor and cannot diagnose you. In an emergency, call your local emergency
            number.{' '}
            <Link to="/help" className="font-medium underline">
              Learn more
            </Link>
          </span>
        </div>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Suspense
            fallback={
              <div className="grid min-h-[50vh] place-items-center text-muted-foreground">
                <Spinner className="size-6" />
              </div>
            }
          >
            <ErrorBoundary resetKey={pathname}>
              <Outlet />
            </ErrorBoundary>
          </Suspense>
        </main>
      </div>
    </div>
  )
}
