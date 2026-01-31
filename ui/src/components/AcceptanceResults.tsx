/**
 * AcceptanceResults Component
 * ===========================
 *
 * Feature #70: Acceptance Results Display Component
 *
 * Displays acceptance gate results with per-validator pass/fail indicators.
 * Used in the RunInspector and DynamicAgentCard to show validation status.
 *
 * Features:
 * - Overall verdict display with color and icon
 * - Per-validator pass/fail badges
 * - Expandable validator messages
 * - Required validator highlighting
 * - Retry count display if > 0
 * - Accessible with proper ARIA attributes
 */

import { useState, useMemo } from 'react'
import {
  CheckCircle,
  XCircle,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Clock,
  Star,
  Check,
  X,
} from 'lucide-react'
import { ValidatorTypeIcon } from './ValidatorTypeIcon'
import type { AgentRunVerdict, AcceptanceValidatorResult } from '../lib/types'

// =============================================================================
// Props Interface
// =============================================================================

/**
 * ValidatorResult - represents a single validator's result
 */
export interface ValidatorResult {
  /** Validator type (e.g., 'test_pass', 'file_exists') */
  type: string
  /** Whether this validator passed */
  passed: boolean
  /** Message describing the result */
  message: string
  /** Index for ordering */
  index?: number
  /** Score if using weighted mode (0-1) */
  score?: number
  /** Whether this is a required validator */
  required?: boolean
  /** Additional details */
  details?: Record<string, unknown>
}

/**
 * Canonical acceptance results format: Record<string, AcceptanceValidatorResult>
 * This is the ONLY format the UI accepts (Feature #161).
 * Both REST API and WebSocket emit this format since Feature #160.
 */
export type CanonicalAcceptanceResults = Record<string, AcceptanceValidatorResult>

/**
 * Props for AcceptanceResults component
 *
 * Feature #161: Strict parser — only accepts canonical Record<string, AcceptanceValidatorResult>.
 * Legacy array formats and other shapes are rejected with a dev-mode warning.
 */
export interface AcceptanceResultsProps {
  /**
   * Acceptance results in canonical format: Record<string, AcceptanceValidatorResult>.
   * Both REST API and WebSocket now emit this format (Feature #160).
   */
  acceptanceResults: CanonicalAcceptanceResults | null
  /** Final verdict (passed/failed/partial) */
  verdict: AgentRunVerdict | null
  /** Gate mode for display context */
  gateMode?: 'all_pass' | 'any_pass' | 'weighted'
  /** Retry count to display (show if > 0) */
  retryCount?: number
  /** Optional className for container styling */
  className?: string
  /** Whether to start expanded (default: false) */
  defaultExpanded?: boolean
  /** Optional minimum score for weighted mode */
  minScore?: number
}

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Validate that a single entry matches AcceptanceValidatorResult shape.
 * Returns true if the entry has the required `passed` (boolean) and `message` (string) fields.
 */
function isValidResultEntry(entry: unknown): entry is AcceptanceValidatorResult {
  if (typeof entry !== 'object' || entry === null) return false
  const obj = entry as Record<string, unknown>
  return typeof obj.passed === 'boolean' && typeof obj.message === 'string'
}

/**
 * Dev-mode warning helper.
 * Emits console.warn only in development builds (import.meta.env.DEV).
 * Feature #161: Strict acceptance results parser.
 */
function devWarn(message: string, payload?: unknown): void {
  if (import.meta.env.DEV) {
    console.warn(`[AcceptanceResults] ${message}`, payload !== undefined ? payload : '')
  }
}

/**
 * Strict parser for canonical acceptance results format.
 *
 * Feature #161: Replaces the multi-format normalizeResults() that tried to handle
 * ValidatorResult[], WSValidatorResult[], and Record<> shapes. Now only accepts
 * the canonical Record<string, AcceptanceValidatorResult> and fails loudly in
 * development mode if an unknown format is received.
 *
 * @param input - Expected: Record<string, AcceptanceValidatorResult> | null
 * @returns ValidatorResult[] for rendering
 */
function parseAcceptanceResults(
  input: CanonicalAcceptanceResults | null
): ValidatorResult[] {
  if (!input) return []

  // Reject arrays — the canonical format is always a Record, never an array
  if (Array.isArray(input)) {
    devWarn(
      'Received array instead of canonical Record<string, AcceptanceValidatorResult>. ' +
      'This is a legacy format that should have been converted by the backend (Feature #160).',
      input
    )
    return []
  }

  // Reject non-object types
  if (typeof input !== 'object') {
    devWarn(
      `Received unexpected type "${typeof input}" instead of canonical Record<string, AcceptanceValidatorResult>.`,
      input
    )
    return []
  }

  const entries = Object.entries(input)

  // Validate each entry matches the expected schema
  const results: ValidatorResult[] = []
  for (let idx = 0; idx < entries.length; idx++) {
    const [type, entry] = entries[idx]

    if (!isValidResultEntry(entry)) {
      devWarn(
        `Entry "${type}" does not match AcceptanceValidatorResult schema ` +
        '(requires { passed: boolean, message: string }). Skipping.',
        entry
      )
      continue
    }

    results.push({
      type,
      passed: entry.passed,
      message: entry.message,
      index: idx,
      score: entry.score,
      required: entry.required,
      details: entry.details,
    })
  }

  return results
}

/**
 * Get a readable label from validator type
 */
function getValidatorLabel(type: string): string {
  const labels: Record<string, string> = {
    test_pass: 'Test Pass',
    file_exists: 'File Exists',
    forbidden_patterns: 'No Forbidden Patterns',
    lint_clean: 'Lint Clean',
    type_check: 'Type Check',
  }
  return labels[type] || type.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

// =============================================================================
// Verdict Badge Component
// =============================================================================

interface VerdictBadgeProps {
  verdict: AgentRunVerdict | null
  className?: string
}

/**
 * VerdictBadge - displays the overall verdict with icon and color
 */
function VerdictBadge({ verdict, className = '' }: VerdictBadgeProps) {
  if (!verdict) {
    return (
      <div
        className={`
          inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md
          text-sm font-medium
          bg-gray-100 dark:bg-gray-800
          text-gray-600 dark:text-gray-400
          border-2 border-gray-200 dark:border-gray-700
          ${className}
        `}
        role="status"
        aria-label="No verdict yet"
      >
        <Clock size={16} aria-hidden="true" />
        <span>Pending</span>
      </div>
    )
  }

  const config: Record<
    AgentRunVerdict,
    { icon: typeof CheckCircle; label: string; colors: string }
  > = {
    passed: {
      icon: CheckCircle,
      label: 'Passed',
      colors: `
        bg-green-100 dark:bg-green-900/30
        text-green-700 dark:text-green-400
        border-2 border-green-300 dark:border-green-600
      `,
    },
    failed: {
      icon: XCircle,
      label: 'Failed',
      colors: `
        bg-red-100 dark:bg-red-900/30
        text-red-700 dark:text-red-400
        border-2 border-red-300 dark:border-red-600
      `,
    },
    partial: {
      icon: AlertCircle,
      label: 'Partial',
      colors: `
        bg-amber-100 dark:bg-amber-900/30
        text-amber-700 dark:text-amber-400
        border-2 border-amber-300 dark:border-amber-600
      `,
    },
    error: {
      icon: AlertCircle,
      label: 'Error',
      colors: `
        bg-orange-100 dark:bg-orange-900/30
        text-orange-700 dark:text-orange-400
        border-2 border-orange-300 dark:border-orange-600
      `,
    },
  }

  const { icon: Icon, label, colors } = config[verdict]

  return (
    <div
      className={`
        inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md
        text-sm font-medium
        ${colors}
        ${className}
      `}
      role="status"
      aria-label={`Verdict: ${label}`}
      data-verdict={verdict}
    >
      <Icon size={16} aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

// =============================================================================
// Validator Item Component
// =============================================================================

interface ValidatorItemProps {
  validator: ValidatorResult
  isExpanded: boolean
  onToggle: () => void
}

/**
 * ValidatorItem - displays a single validator with pass/fail badge and expandable message
 * Feature #74: Now includes validator type icons
 */
function ValidatorItem({ validator, isExpanded, onToggle }: ValidatorItemProps) {
  const label = getValidatorLabel(validator.type)

  return (
    <div
      className={`
        neo-card-flat border-l-4
        ${validator.passed
          ? 'border-l-green-500'
          : 'border-l-red-500'
        }
        transition-all duration-200
      `}
      data-testid={`validator-item-${validator.type}`}
      data-passed={validator.passed}
    >
      {/* Header - clickable to expand */}
      <button
        className={`
          w-full p-3 text-left
          flex items-center justify-between gap-2
          hover:bg-neo-neutral-50 dark:hover:bg-neo-neutral-800
          focus:outline-none focus-visible:ring-2 focus-visible:ring-neo-accent
          rounded-t-md
        `}
        onClick={onToggle}
        aria-expanded={isExpanded}
        aria-controls={`validator-details-${validator.type}`}
      >
        <div className="flex items-center gap-2 min-w-0 flex-1">
          {/* Pass/Fail icon */}
          {validator.passed ? (
            <span className="flex-shrink-0 w-5 h-5 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
              <Check size={12} className="text-green-600 dark:text-green-400" aria-hidden="true" />
            </span>
          ) : (
            <span className="flex-shrink-0 w-5 h-5 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
              <X size={12} className="text-red-600 dark:text-red-400" aria-hidden="true" />
            </span>
          )}

          {/* Feature #74: Validator type icon - Step 7 */}
          <ValidatorTypeIcon
            validatorType={validator.type}
            size={14}
            className="text-neo-text-secondary flex-shrink-0"
          />

          {/* Validator name */}
          <span className="font-medium text-sm truncate">{label}</span>

          {/* Required badge */}
          {validator.required && (
            <span
              className="
                inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium
                bg-amber-100 dark:bg-amber-900/30
                text-amber-700 dark:text-amber-400
              "
              title="Required validator"
            >
              <Star size={10} aria-hidden="true" fill="currentColor" />
              Required
            </span>
          )}
        </div>

        {/* Pass/Fail badge and expand icon */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <span
            className={`
              neo-badge text-[10px] px-1.5 py-0.5
              ${validator.passed
                ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
              }
            `}
          >
            {validator.passed ? 'PASS' : 'FAIL'}
          </span>

          {/* Score if using weighted mode */}
          {validator.score !== undefined && (
            <span className="text-xs text-neo-text-muted font-mono">
              {(validator.score * 100).toFixed(0)}%
            </span>
          )}

          {isExpanded ? (
            <ChevronUp size={14} className="text-neo-text-secondary" aria-hidden="true" />
          ) : (
            <ChevronDown size={14} className="text-neo-text-secondary" aria-hidden="true" />
          )}
        </div>
      </button>

      {/* Expanded details */}
      {isExpanded && (
        <div
          id={`validator-details-${validator.type}`}
          className="
            px-3 pb-3 pt-0
            border-t border-neo-border/30
          "
        >
          {/* Message */}
          <p className="text-xs text-neo-text-secondary mt-2 whitespace-pre-wrap">
            {validator.message || 'No message provided'}
          </p>

          {/* Additional details */}
          {validator.details && Object.keys(validator.details).length > 0 && (
            <pre
              className="
                mt-2 p-2 rounded text-[10px] font-mono
                bg-neo-neutral-100 dark:bg-neo-neutral-800
                overflow-x-auto max-h-32
              "
            >
              {JSON.stringify(validator.details, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// Main AcceptanceResults Component
// =============================================================================

export function AcceptanceResults({
  acceptanceResults,
  verdict,
  gateMode = 'all_pass',
  retryCount = 0,
  className = '',
  defaultExpanded = false,
  minScore,
}: AcceptanceResultsProps) {
  // Feature #161: Strict parser — only accepts canonical Record format
  const validators = useMemo(
    () => parseAcceptanceResults(acceptanceResults),
    [acceptanceResults]
  )

  // Track which validators are expanded
  const [expandedValidators, setExpandedValidators] = useState<Set<string>>(
    () => (defaultExpanded ? new Set(validators.map(v => v.type)) : new Set())
  )

  // Calculate summary statistics
  const passedCount = validators.filter(v => v.passed).length
  const totalCount = validators.length

  // Toggle a validator's expanded state
  const toggleValidator = (type: string) => {
    setExpandedValidators(prev => {
      const next = new Set(prev)
      if (next.has(type)) {
        next.delete(type)
      } else {
        next.add(type)
      }
      return next
    })
  }

  // Empty state
  if (validators.length === 0 && !verdict) {
    return (
      <div
        className={`
          flex flex-col items-center justify-center py-8
          text-neo-text-secondary
          ${className}
        `}
      >
        <Clock size={32} className="mb-2 opacity-50" aria-hidden="true" />
        <p className="text-sm">No acceptance results yet</p>
        <p className="text-xs mt-1 opacity-75">
          Results will appear after validation runs
        </p>
      </div>
    )
  }

  return (
    <div
      className={`flex flex-col gap-4 ${className}`}
      data-testid="acceptance-results"
    >
      {/* Header with verdict and summary */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Verdict badge */}
        <VerdictBadge verdict={verdict} />

        {/* Summary stats */}
        <div className="flex items-center gap-3 text-xs text-neo-text-secondary">
          {/* Pass/Fail counts */}
          {totalCount > 0 && (
            <span className="flex items-center gap-1">
              <Check size={12} className="text-green-600 dark:text-green-400" aria-hidden="true" />
              <span className="font-medium">{passedCount}</span>
              <span className="text-neo-text-muted">/</span>
              <span>{totalCount}</span>
            </span>
          )}

          {/* Gate mode indicator */}
          <span
            className="px-2 py-0.5 rounded bg-neo-neutral-100 dark:bg-neo-neutral-800 font-mono text-[10px]"
            title={`Gate mode: ${gateMode}`}
          >
            {gateMode === 'all_pass' && 'ALL'}
            {gateMode === 'any_pass' && 'ANY'}
            {gateMode === 'weighted' && `≥${(minScore ?? 0) * 100}%`}
          </span>

          {/* Retry count */}
          {retryCount > 0 && (
            <span
              className="flex items-center gap-1 text-amber-600 dark:text-amber-400"
              title={`${retryCount} retry attempt${retryCount > 1 ? 's' : ''}`}
            >
              <RefreshCw size={12} aria-hidden="true" />
              <span className="font-medium">{retryCount}</span>
            </span>
          )}
        </div>
      </div>

      {/* Validator list */}
      {validators.length > 0 && (
        <div
          className="flex flex-col gap-2"
          role="list"
          aria-label="Validator results"
        >
          {validators.map((validator, idx) => (
            <div key={`${validator.type}-${idx}`} role="listitem">
              <ValidatorItem
                validator={validator}
                isExpanded={expandedValidators.has(validator.type)}
                onToggle={() => toggleValidator(validator.type)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Export subcomponents for direct use
export { VerdictBadge }
export default AcceptanceResults
