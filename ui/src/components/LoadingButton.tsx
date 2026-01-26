/**
 * LoadingButton Component
 * =======================
 *
 * A button component with built-in loading spinner support.
 * Used for action buttons like pause, cancel, etc.
 *
 * Features:
 * - Shows spinner while loading
 * - Disables interaction during loading
 * - Supports all neo-btn variants
 * - Accessible with aria attributes
 */

import { Loader2 } from 'lucide-react'
import type { ReactNode, ButtonHTMLAttributes } from 'react'

interface LoadingButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Whether the button is in loading state */
  isLoading?: boolean
  /** Loading text to show (optional, defaults to hiding text) */
  loadingText?: string
  /** Button variant */
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'danger' | 'ghost'
  /** Button size */
  size?: 'sm' | 'md' | 'lg' | 'icon'
  /** Icon to show before text */
  icon?: ReactNode
  /** Button content */
  children?: ReactNode
}

const variantClasses: Record<string, string> = {
  default: '',
  primary: 'neo-btn-primary',
  success: 'neo-btn-success',
  warning: 'neo-btn-warning',
  danger: 'neo-btn-danger',
  ghost: 'neo-btn-ghost',
}

const sizeClasses: Record<string, string> = {
  sm: 'neo-btn-sm',
  md: '',
  lg: 'neo-btn-lg',
  icon: 'neo-btn-icon',
}

export function LoadingButton({
  isLoading = false,
  loadingText,
  variant = 'default',
  size = 'md',
  icon,
  children,
  className = '',
  disabled,
  ...props
}: LoadingButtonProps) {
  const isDisabled = disabled || isLoading

  return (
    <button
      className={`
        neo-btn
        ${variantClasses[variant]}
        ${sizeClasses[size]}
        ${isLoading ? 'neo-btn-loading' : ''}
        ${className}
      `}
      disabled={isDisabled}
      aria-busy={isLoading}
      aria-disabled={isDisabled}
      {...props}
    >
      {isLoading ? (
        <>
          <Loader2
            size={size === 'sm' ? 14 : size === 'lg' ? 20 : 16}
            className="animate-spin"
            aria-hidden="true"
          />
          {loadingText && <span>{loadingText}</span>}
        </>
      ) : (
        <>
          {icon}
          {children}
        </>
      )}
    </button>
  )
}

/**
 * ActionButton - Specialized button for agent actions (pause, cancel, etc.)
 * with optimistic feedback and error recovery
 */
interface ActionButtonProps {
  /** Action name for accessibility */
  actionName: string
  /** Icon to display */
  icon: ReactNode
  /** Click handler - should return a promise */
  onClick: () => Promise<void>
  /** Button variant */
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'danger'
  /** Size */
  size?: 'sm' | 'md' | 'icon'
  /** Additional className */
  className?: string
  /** Disabled state */
  disabled?: boolean
  /** Title for tooltip */
  title?: string
}

export function ActionButton({
  actionName,
  icon,
  onClick,
  variant = 'default',
  size = 'sm',
  className = '',
  disabled = false,
  title,
}: ActionButtonProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleClick = async () => {
    if (isLoading || disabled) return

    setIsLoading(true)
    setError(null)

    try {
      await onClick()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Action failed'
      setError(message)
      // Clear error after 3 seconds
      setTimeout(() => setError(null), 3000)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="relative">
      <LoadingButton
        isLoading={isLoading}
        variant={error ? 'danger' : variant}
        size={size}
        icon={icon}
        onClick={handleClick}
        disabled={disabled}
        title={error || title || actionName}
        aria-label={actionName}
        className={className}
      />
      {/* Error tooltip */}
      {error && (
        <div
          className="
            absolute -top-8 left-1/2 -translate-x-1/2
            px-2 py-1 text-xs bg-neo-danger text-white
            rounded whitespace-nowrap z-50
            animate-slide-in-bottom
          "
          role="alert"
        >
          {error}
        </div>
      )}
    </div>
  )
}

// Need useState for ActionButton
import { useState } from 'react'

export default LoadingButton
