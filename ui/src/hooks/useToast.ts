/**
 * Lightweight toast notification system for surfacing mutation errors.
 *
 * Uses a simple global event emitter pattern so toasts can be triggered
 * from React Query hooks without needing React context. The ToastContainer
 * component subscribes to these events and renders the notifications.
 *
 * Usage from hooks:
 *   import { toast } from '../hooks/useToast'
 *   onError: (error) => toast.error('Failed to create project', error.message)
 *
 * Usage in components:
 *   import { useToastState } from '../hooks/useToast'
 *   const { toasts, removeToast } = useToastState()
 */

import { useState, useEffect, useCallback } from 'react'

// ============================================================================
// Types
// ============================================================================

export type ToastType = 'error' | 'success' | 'warning' | 'info'

export interface Toast {
  id: string
  type: ToastType
  title: string
  message: string
  /** Duration in ms before auto-dismiss. Default: 6000 for errors, 4000 for others */
  duration: number
}

type ToastListener = (toast: Toast) => void

// ============================================================================
// Global Event Emitter (framework-agnostic)
// ============================================================================

const listeners = new Set<ToastListener>()
let nextId = 0

function emit(type: ToastType, title: string, message?: string) {
  const id = `toast-${++nextId}-${Date.now()}`
  const duration = type === 'error' ? 6000 : 4000
  const toastObj: Toast = {
    id,
    type,
    title,
    message: message ?? '',
    duration,
  }
  listeners.forEach((fn) => fn(toastObj))
}

/**
 * Global toast API — call from anywhere (hooks, callbacks, etc.)
 *
 * @example
 *   toast.error('Delete failed', error.message)
 *   toast.success('Project created')
 */
export const toast = {
  error: (title: string, message?: string) => emit('error', title, message),
  success: (title: string, message?: string) => emit('success', title, message),
  warning: (title: string, message?: string) => emit('warning', title, message),
  info: (title: string, message?: string) => emit('info', title, message),
}

// ============================================================================
// React Hook — subscribe to toast events
// ============================================================================

/**
 * Hook for the ToastContainer component. Subscribes to the global
 * toast emitter and manages the visible toast list.
 */
export function useToastState() {
  const [toasts, setToasts] = useState<Toast[]>([])

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  useEffect(() => {
    const handler: ToastListener = (newToast) => {
      setToasts((prev) => [...prev, newToast])

      // Auto-dismiss
      if (newToast.duration > 0) {
        setTimeout(() => {
          removeToast(newToast.id)
        }, newToast.duration)
      }
    }

    listeners.add(handler)
    return () => {
      listeners.delete(handler)
    }
  }, [removeToast])

  return { toasts, removeToast }
}
