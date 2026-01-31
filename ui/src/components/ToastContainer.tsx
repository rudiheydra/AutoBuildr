/**
 * Toast notification container component.
 *
 * Renders a stack of toast notifications in the bottom-right corner.
 * Uses the neobrutalism design system with bold borders and bright colors.
 * Each toast auto-dismisses and can be manually closed.
 */

import { useEffect, useState } from 'react'
import { X, AlertTriangle, CheckCircle, Info, AlertCircle } from 'lucide-react'
import type { Toast, ToastType } from '../hooks/useToast'

// ============================================================================
// Style Config
// ============================================================================

const TOAST_STYLES: Record<
  ToastType,
  { bg: string; border: string; icon: typeof AlertTriangle; iconColor: string }
> = {
  error: {
    bg: 'bg-red-50 dark:bg-red-950/60',
    border: 'border-red-500',
    icon: AlertTriangle,
    iconColor: 'text-red-600 dark:text-red-400',
  },
  success: {
    bg: 'bg-green-50 dark:bg-green-950/60',
    border: 'border-green-500',
    icon: CheckCircle,
    iconColor: 'text-green-600 dark:text-green-400',
  },
  warning: {
    bg: 'bg-amber-50 dark:bg-amber-950/60',
    border: 'border-amber-500',
    icon: AlertCircle,
    iconColor: 'text-amber-600 dark:text-amber-400',
  },
  info: {
    bg: 'bg-blue-50 dark:bg-blue-950/60',
    border: 'border-blue-500',
    icon: Info,
    iconColor: 'text-blue-600 dark:text-blue-400',
  },
}

// ============================================================================
// Single Toast Item
// ============================================================================

function ToastItem({
  toast,
  onDismiss,
}: {
  toast: Toast
  onDismiss: (id: string) => void
}) {
  const [visible, setVisible] = useState(false)
  const style = TOAST_STYLES[toast.type]
  const Icon = style.icon

  // Animate in on mount
  useEffect(() => {
    const frame = requestAnimationFrame(() => setVisible(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  const handleDismiss = () => {
    setVisible(false)
    // Wait for exit animation before removing
    setTimeout(() => onDismiss(toast.id), 200)
  }

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={[
        // Base layout
        'flex items-start gap-3 p-4 rounded-lg',
        // Neobrutalism: bold border + shadow
        'border-2',
        style.border,
        style.bg,
        'shadow-[3px_3px_0px_0px_rgba(0,0,0,0.15)]',
        // Sizing
        'w-[380px] max-w-[calc(100vw-2rem)]',
        // Animation
        'transition-all duration-200 ease-out',
        visible
          ? 'opacity-100 translate-x-0'
          : 'opacity-0 translate-x-4',
      ].join(' ')}
    >
      {/* Icon */}
      <div className={`flex-shrink-0 mt-0.5 ${style.iconColor}`}>
        <Icon size={20} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {toast.title && (
          <p className="font-bold text-sm text-[var(--color-neo-text)] mb-0.5">
            {toast.title}
          </p>
        )}
        <p className="text-sm text-[var(--color-neo-text-secondary)] break-words">
          {toast.message}
        </p>
      </div>

      {/* Dismiss button */}
      <button
        onClick={handleDismiss}
        className="flex-shrink-0 p-0.5 rounded hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
        aria-label="Dismiss notification"
      >
        <X size={16} className="text-[var(--color-neo-text-muted)]" />
      </button>
    </div>
  )
}

// ============================================================================
// Container
// ============================================================================

export function ToastContainer({
  toasts,
  onDismiss,
}: {
  toasts: Toast[]
  onDismiss: (id: string) => void
}) {
  if (toasts.length === 0) return null

  return (
    <div
      aria-label="Notifications"
      className="fixed bottom-4 right-4 z-[9999] flex flex-col-reverse gap-2 pointer-events-none"
    >
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <ToastItem toast={toast} onDismiss={onDismiss} />
        </div>
      ))}
    </div>
  )
}
