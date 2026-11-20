import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'

export function Logo({ to = '/', className }: { to?: string; className?: string }) {
  return (
    <Link to={to} className={cn('flex items-center gap-2 font-semibold text-primary', className)}>
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
        <rect width="32" height="32" rx="8" fill="currentColor" />
        <path d="M13 7h6v6h6v6h-6v6h-6v-6H7v-6h6z" fill="#2dd4bf" />
      </svg>
      <span className="text-[1.05rem]">
        MediCore <span className="text-teal">AI</span>
      </span>
    </Link>
  )
}
