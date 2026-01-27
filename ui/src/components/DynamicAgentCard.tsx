/**
 * DynamicAgentCard Component
 * ==========================
 *
 * Displays an AgentSpec execution with dynamic status coloring.
 * Used in the Phase 3 UI to show real-time agent execution status.
 *
 * Features:
 * - Status color coding based on AgentRun status
 * - Pulse animation for running status
 * - Progress bar showing turns_used / max_turns
 * - Accessibility considerations with proper contrast ratios
 * - Animated thinking state indicator showing current activity
 */

import { Clock, AlertCircle, CheckCircle, PauseCircle, XCircle, Timer, Play, ExternalLink, Check, X, Brain, Code, TestTube, Shield } from 'lucide-react'
import { TurnsProgressBar } from './TurnsProgressBar'
import type { AgentRunStatus, DynamicAgentData, AgentRun, ThinkingState, AgentEventType } from '../lib/types'

interface DynamicAgentCardProps {
  data: DynamicAgentData
  latestEventType?: AgentEventType | null
  onClick?: () => void
  /** Tab index for keyboard navigation (from useAgentCardGridNavigation) */
  tabIndex?: number
  /** Whether the card is selected/focused in the grid */
  'aria-selected'?: boolean
  /** Card index in the grid (for navigation) */
  'data-card-index'?: number
  /** Custom keydown handler from navigation hook */
  onKeyDown?: (e: React.KeyboardEvent) => void
  /** Custom focus handler from navigation hook */
  onFocus?: () => void
  /** Ref callback from navigation hook */
  cardRef?: (el: HTMLElement | null) => void
}

/**
 * Get status icon based on AgentRun status
 */
function getStatusIcon(status: AgentRunStatus) {
  switch (status) {
    case 'pending':
      return Clock
    case 'running':
      return Play
    case 'paused':
      return PauseCircle
    case 'completed':
      return CheckCircle
    case 'failed':
      return XCircle
    case 'timeout':
      return Timer
    default:
      return AlertCircle
  }
}

/**
 * Get human-readable status label
 */
function getStatusLabel(status: AgentRunStatus): string {
  switch (status) {
    case 'pending':
      return 'Pending'
    case 'running':
      return 'Running'
    case 'paused':
      return 'Paused'
    case 'completed':
      return 'Completed'
    case 'failed':
      return 'Failed'
    case 'timeout':
      return 'Timed Out'
    default:
      return 'Unknown'
  }
}

/**
 * Get task type icon/emoji
 */
function getTaskTypeEmoji(taskType: string): string {
  switch (taskType) {
    case 'coding':
      return '💻'
    case 'testing':
      return '🧪'
    case 'refactoring':
      return '🔧'
    case 'documentation':
      return '📝'
    case 'audit':
      return '🔍'
    case 'custom':
      return '⚙️'
    default:
      return '🤖'
  }
}

// ============================================================================
// Thinking State Animation System
// ============================================================================

/**
 * Derive thinking state from the latest event type
 * Maps event types to thinking states for animation:
 * - tool_call -> coding (working)
 * - turn_complete -> thinking
 * - acceptance_check -> validating
 */
export function deriveThinkingState(
  latestEventType: AgentEventType | null | undefined,
  status: AgentRunStatus
): ThinkingState {
  // Only show thinking states when running
  if (status !== 'running') {
    return 'idle'
  }

  // No event yet - initial thinking state
  if (!latestEventType) {
    return 'thinking'
  }

  // Map event types to thinking states
  switch (latestEventType) {
    case 'tool_call':
    case 'tool_result':
      // Working/coding when tools are being used
      return 'coding'
    case 'turn_complete':
    case 'started':
      // Thinking after turn complete, waiting for next action
      return 'thinking'
    case 'acceptance_check':
      // Validating when running acceptance checks
      return 'validating'
    default:
      // Default to thinking for other states
      return 'thinking'
  }
}

/**
 * Get thinking state label for display
 */
function getThinkingStateLabel(state: ThinkingState): string {
  switch (state) {
    case 'thinking':
      return 'Thinking...'
    case 'coding':
      return 'Coding...'
    case 'testing':
      return 'Testing...'
    case 'validating':
      return 'Validating...'
    default:
      return ''
  }
}

/**
 * Get thinking state icon component
 */
function getThinkingStateIcon(state: ThinkingState) {
  switch (state) {
    case 'thinking':
      return Brain
    case 'coding':
      return Code
    case 'testing':
      return TestTube
    case 'validating':
      return Shield
    default:
      return null
  }
}

/**
 * Get CSS animation class for thinking state
 */
function getThinkingStateAnimation(state: ThinkingState): string {
  switch (state) {
    case 'thinking':
      return 'animate-thinking'
    case 'coding':
      return 'animate-working'
    case 'testing':
      return 'animate-testing'
    case 'validating':
      return 'animate-pulse-neo'
    default:
      return ''
  }
}

/**
 * ThinkingStateIndicator Component
 * Displays animated indicator showing current agent activity state
 */
export function ThinkingStateIndicator({
  state,
  className = ''
}: {
  state: ThinkingState
  className?: string
}) {
  // Don't render if idle
  if (state === 'idle') {
    return null
  }

  const Icon = getThinkingStateIcon(state)
  const label = getThinkingStateLabel(state)
  const animationClass = getThinkingStateAnimation(state)

  if (!Icon) {
    return null
  }

  return (
    <div
      className={`
        inline-flex items-center gap-1.5 px-2 py-1 rounded-md
        text-xs font-medium
        bg-[var(--color-status-running-bg)]
        text-[var(--color-status-running-text)]
        ${className}
      `}
      role="status"
      aria-live="polite"
      aria-label={label}
      data-testid="thinking-state-indicator"
      data-thinking-state={state}
    >
      <span className={animationClass}>
        <Icon size={14} aria-hidden="true" />
      </span>
      <span className="animate-pulse">{label}</span>
    </div>
  )
}

// ============================================================================
// Status Components
// ============================================================================

/**
 * AgentRun Status Badge component
 * Displays status with appropriate color coding
 * Includes ARIA attributes for screen reader accessibility
 * Features pattern/icon fallbacks for high contrast mode (Feature #83)
 */
function StatusBadge({ status }: { status: AgentRunStatus }) {
  const Icon = getStatusIcon(status)
  const label = getStatusLabel(status)

  return (
    <span
      className={`neo-status-badge neo-status-${status}`}
      role="status"
      aria-live="polite"
      aria-label={`Agent status: ${label}`}
      data-status={status}
    >
      {/* Icon wrapper with pattern fallback indicator class */}
      <span className="neo-status-indicator-pattern" data-status={status}>
        <Icon size={14} aria-hidden="true" />
      </span>
      {label}
    </span>
  )
}

// TurnsProgressBar is now imported from ./TurnsProgressBar

/**
 * Truncate error message to specified length
 * Returns truncated message with ellipsis if needed
 */
function truncateError(error: string, maxLength: number = 100): { truncated: string; wasLong: boolean } {
  if (error.length <= maxLength) {
    return { truncated: error, wasLong: false }
  }
  return { truncated: error.slice(0, maxLength) + '...', wasLong: true }
}

/**
 * ErrorDisplay Component
 * Displays error information when run.status is 'failed' or 'timeout'
 * with error icon, truncated message, and View Details link
 */
interface ErrorDisplayProps {
  status: AgentRunStatus
  error: string | null
  onClick?: () => void
}

function ErrorDisplay({ status, error, onClick }: ErrorDisplayProps) {
  // Only show for failed or timeout status
  const isErrorStatus = status === 'failed' || status === 'timeout'
  if (!isErrorStatus) return null

  // Generate error message based on status
  const errorMessage = error || (status === 'timeout' ? 'Execution timed out' : 'Unknown error')
  const { truncated, wasLong } = truncateError(errorMessage)

  // Determine colors based on status (timeout uses orange, failed uses red)
  const isTimeout = status === 'timeout'
  const bgColor = isTimeout ? 'bg-[var(--color-status-timeout-bg)]' : 'bg-[var(--color-status-failed-bg)]'
  const textColor = isTimeout ? 'text-[var(--color-status-timeout-text)]' : 'text-[var(--color-status-failed-text)]'
  const iconColor = isTimeout ? 'text-[var(--color-status-timeout-text)]' : 'text-[var(--color-status-failed-text)]'

  // Use appropriate icon based on status
  const ErrorIcon = isTimeout ? Timer : AlertCircle

  const handleViewDetails = (e: React.MouseEvent) => {
    e.stopPropagation() // Prevent card click from firing
    onClick?.()
  }

  return (
    <div
      className={`mt-2 p-2 rounded text-xs ${bgColor} ${textColor}`}
      data-testid="error-display"
    >
      {/* Header with icon */}
      <div className="flex items-start gap-1.5">
        <ErrorIcon
          size={14}
          className={`flex-shrink-0 mt-0.5 ${iconColor}`}
          aria-hidden="true"
        />
        <div className="flex-1 min-w-0">
          <p
            className="font-medium"
            title={wasLong ? errorMessage : undefined}
          >
            {truncated}
          </p>
        </div>
      </div>

      {/* View Details link - min 44px touch target for mobile */}
      <button
        onClick={handleViewDetails}
        className={`
          mt-1.5 flex items-center gap-1 text-[11px] sm:text-[11px] font-medium
          hover:underline focus:underline focus:outline-none
          min-h-[44px] sm:min-h-0 py-2 sm:py-0 touch-manipulation
          ${textColor}
        `}
        aria-label="View error details in inspector"
        data-testid="view-details-link"
      >
        <ExternalLink size={10} aria-hidden="true" />
        View Details
      </button>
    </div>
  )
}

/**
 * ValidatorStatusIndicators Component
 * Displays a compact summary of acceptance/validator results
 */
function ValidatorStatusIndicators({ run }: { run: AgentRun }) {
  const results = run.acceptance_results as Record<string, { passed: boolean; message: string }> | null

  if (!results || Object.keys(results).length === 0) {
    return null
  }

  const entries = Object.entries(results)
  const passedCount = entries.filter(([, r]) => r.passed).length
  const totalCount = entries.length
  const allPassed = passedCount === totalCount

  return (
    <div className="mt-2">
      {/* Summary line */}
      <div className="flex items-center gap-1.5 text-xs">
        <span className="text-neo-text-secondary">Validators:</span>
        <span className={allPassed ? 'text-[var(--color-status-completed-text)]' : 'text-[var(--color-status-failed-text)]'}>
          {passedCount}/{totalCount}
        </span>
      </div>

      {/* Individual validator indicators */}
      <div className="flex flex-wrap gap-1 mt-1.5">
        {entries.map(([name, result]) => (
          <span
            key={name}
            className={`
              inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-medium rounded
              ${result.passed
                ? 'bg-[var(--color-status-completed-bg)] text-[var(--color-status-completed-text)]'
                : 'bg-[var(--color-status-failed-bg)] text-[var(--color-status-failed-text)]'
              }
            `}
            title={result.message}
          >
            {result.passed ? <Check size={10} /> : <X size={10} />}
            <span className="max-w-16 truncate">{name}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

/**
 * DynamicAgentCard - Main component
 *
 * Supports keyboard navigation when used with useAgentCardGridNavigation hook.
 * Implements ARIA grid pattern for accessible navigation.
 *
 * Features (Feature #80):
 * - tabIndex management via navigation hook
 * - Enter/Space to open inspector
 * - Arrow keys navigation (via parent hook)
 * - Focus visible indicator (neo-agent-card-focusable class)
 * - Screen reader announcements for status changes (via StatusBadge aria-live)
 */
export function DynamicAgentCard({
  data,
  latestEventType,
  onClick,
  tabIndex: tabIndexProp,
  'aria-selected': ariaSelected,
  'data-card-index': dataCardIndex,
  onKeyDown: onKeyDownProp,
  onFocus: onFocusProp,
  cardRef,
}: DynamicAgentCardProps) {
  const { spec, run } = data
  const status: AgentRunStatus = run?.status ?? 'pending'
  const isActive = status === 'running'
  const icon = spec.icon || getTaskTypeEmoji(spec.task_type)

  // Derive thinking state from latest event type
  const thinkingState = deriveThinkingState(latestEventType, status)

  // Use provided tabIndex from navigation hook, or default to 0
  const tabIndex = tabIndexProp !== undefined ? tabIndexProp : 0

  // Combined keydown handler - supports both navigation and selection
  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Call the navigation hook's keydown handler first (for arrow keys)
    onKeyDownProp?.(e)

    // If not already handled by navigation, check for Enter/Space to open inspector
    if (!e.defaultPrevented) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        onClick?.()
      }
    }
  }

  // Focus handler for tracking focused card
  const handleFocus = () => {
    onFocusProp?.()
  }

  return (
    <div
      ref={cardRef}
      className={`
        neo-card neo-agent-card-focusable p-4 sm:p-4 cursor-pointer
        min-h-[120px] touch-manipulation
        ${isActive ? 'animate-pulse-neo' : ''}
        transition-all duration-300
      `}
      onClick={onClick}
      role="gridcell"
      tabIndex={tabIndex}
      onKeyDown={handleKeyDown}
      onFocus={handleFocus}
      aria-label={`${spec.display_name} - ${getStatusLabel(status)}`}
      aria-selected={ariaSelected}
      data-card-index={dataCardIndex}
      data-status={status}
      data-testid="dynamic-agent-card"
    >
      {/* Header with icon and name */}
      <div className="flex items-start gap-3 mb-3">
        <span className="text-2xl" role="img" aria-label={spec.task_type}>
          {icon}
        </span>
        <div className="flex-1 min-w-0">
          <h3 className="font-display font-bold text-sm truncate" title={spec.display_name}>
            {spec.display_name}
          </h3>
          <p className="text-xs text-neo-text-secondary truncate" title={spec.name}>
            {spec.name}
          </p>
        </div>
      </div>

      {/* Status badge and thinking state indicator */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <StatusBadge status={status} />
        <ThinkingStateIndicator state={thinkingState} />
      </div>

      {/* Additional run info */}
      {run && (
        <>
          {/* Progress bar - using reusable TurnsProgressBar component */}
          <TurnsProgressBar
            used={run.turns_used}
            max={spec.max_turns}
            status={status}
            className="mt-3"
          />

          {/* Validator status indicators */}
          <ValidatorStatusIndicators run={run} />

          {/* Error display for failed/timeout status */}
          <ErrorDisplay status={status} error={run.error} onClick={onClick} />

          {/* Token usage */}
          {(run.tokens_in > 0 || run.tokens_out > 0) && (
            <div className="mt-2 flex justify-between text-xs text-neo-text-muted">
              <span>In: {run.tokens_in.toLocaleString()}</span>
              <span>Out: {run.tokens_out.toLocaleString()}</span>
            </div>
          )}
        </>
      )}

      {/* Feature link if available */}
      {spec.source_feature_id && (
        <div className="mt-2 pt-2 border-t border-neo-border/30">
          <span className="text-xs text-neo-text-secondary">
            Feature #{spec.source_feature_id}
          </span>
        </div>
      )}
    </div>
  )
}

/**
 * Export status utility functions for use in other components
 */
export { getStatusIcon, getStatusLabel, StatusBadge, ValidatorStatusIndicators, ErrorDisplay, truncateError }

// Export thinking state utilities for use in other components
export { getThinkingStateLabel, getThinkingStateIcon, getThinkingStateAnimation }

// Re-export TurnsProgressBar from its module for convenience
export { TurnsProgressBar } from './TurnsProgressBar'
