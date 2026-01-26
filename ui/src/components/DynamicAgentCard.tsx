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
 */

import { Clock, AlertCircle, CheckCircle, PauseCircle, XCircle, Timer, Play } from 'lucide-react'
import { TurnsProgressBar } from './TurnsProgressBar'
import type { AgentRunStatus, DynamicAgentData } from '../lib/types'

interface DynamicAgentCardProps {
  data: DynamicAgentData
  onClick?: () => void
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

/**
 * AgentRun Status Badge component
 * Displays status with appropriate color coding
 */
function StatusBadge({ status }: { status: AgentRunStatus }) {
  const Icon = getStatusIcon(status)
  const label = getStatusLabel(status)

  return (
    <span className={`neo-status-badge neo-status-${status}`}>
      <Icon size={14} />
      {label}
    </span>
  )
}

// TurnsProgressBar is now imported from ./TurnsProgressBar

/**
 * DynamicAgentCard - Main component
 */
export function DynamicAgentCard({ data, onClick }: DynamicAgentCardProps) {
  const { spec, run } = data
  const status: AgentRunStatus = run?.status ?? 'pending'
  const isActive = status === 'running'
  const icon = spec.icon || getTaskTypeEmoji(spec.task_type)

  return (
    <div
      className={`
        neo-card p-4 cursor-pointer
        ${isActive ? 'animate-pulse-neo' : ''}
        transition-all duration-300
      `}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          onClick?.()
        }
      }}
      aria-label={`${spec.display_name} - ${getStatusLabel(status)}`}
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

      {/* Status badge */}
      <div className="mb-2">
        <StatusBadge status={status} />
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

          {/* Error message if failed */}
          {run.error && status === 'failed' && (
            <div className="mt-2 p-2 rounded text-xs bg-[var(--color-status-failed-bg)] text-[var(--color-status-failed-text)]">
              <p className="line-clamp-2" title={run.error}>
                {run.error}
              </p>
            </div>
          )}

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
export { getStatusIcon, getStatusLabel, StatusBadge }

// Re-export TurnsProgressBar from its module for convenience
export { TurnsProgressBar } from './TurnsProgressBar'
