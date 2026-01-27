/**
 * RunInspector Component
 * ======================
 *
 * A slide-out panel for inspecting AgentRun details.
 * Shows event timeline, artifacts, and acceptance results.
 *
 * Features:
 * - Tabbed interface (Timeline, Artifacts, Acceptance)
 * - Loading states with skeletons
 * - Action buttons (pause, cancel) with loading spinners
 * - Optimistic updates with error revert
 * - Accessible with keyboard navigation
 * - Slide in from right with animation
 * - Close on Escape key or overlay click
 * - Responsive width for mobile
 *
 * Can be used in two modes:
 * 1. Provide `data` prop directly (DynamicAgentData)
 * 2. Provide `runId` prop to fetch data automatically
 */

import { useState, useCallback, useEffect } from 'react'
import {
  X,
  Pause,
  Play,
  Square,
  Clock,
  AlertCircle,
  CheckCircle,
  XCircle,
} from 'lucide-react'
import { EventTimeline } from './EventTimeline'
import { ArtifactList } from './ArtifactList'
import { StatusBadge } from './DynamicAgentCard'
import { TurnsProgressBar } from './TurnsProgressBar'
import { RunInspectorSkeleton } from './Skeleton'
import { LoadingButton } from './LoadingButton'
import type { DynamicAgentData, AgentRunStatus, AgentRunVerdict, AgentRun, AgentSpecSummary } from '../lib/types'

// =============================================================================
// Props Interface
// =============================================================================

interface BaseRunInspectorProps {
  /** Whether the panel is open */
  isOpen: boolean
  /** Callback to close the panel */
  onClose: () => void
  /** Callback for pause action */
  onPause?: (runId: string) => Promise<void>
  /** Callback for resume action */
  onResume?: (runId: string) => Promise<void>
  /** Callback for cancel action */
  onCancel?: (runId: string) => Promise<void>
}

interface DataModeProps extends BaseRunInspectorProps {
  /** The spec and run data to display (data mode) */
  data: DynamicAgentData | null
  /** Whether data is loading */
  isLoading?: boolean
  /** Error message if loading failed */
  error?: string | null
  /** Not used in data mode */
  runId?: never
}

interface RunIdModeProps extends BaseRunInspectorProps {
  /** The run ID to fetch details for (fetch mode) */
  runId: string
  /** Not used in runId mode */
  data?: never
  /** Not used in runId mode */
  isLoading?: never
  /** Not used in runId mode */
  error?: never
}

type RunInspectorProps = DataModeProps | RunIdModeProps

// =============================================================================
// Tab Types
// =============================================================================

type TabId = 'timeline' | 'artifacts' | 'acceptance'

interface TabConfig {
  id: TabId
  label: string
}

const TABS: TabConfig[] = [
  { id: 'timeline', label: 'Timeline' },
  { id: 'artifacts', label: 'Artifacts' },
  { id: 'acceptance', label: 'Acceptance' },
]

// =============================================================================
// Verdict Badge Component
// =============================================================================

function VerdictBadge({ verdict }: { verdict: AgentRunVerdict | null }) {
  if (!verdict) return null

  const config: Record<AgentRunVerdict, { icon: typeof CheckCircle; color: string; label: string }> = {
    passed: {
      icon: CheckCircle,
      color: 'text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-900/30',
      label: 'Passed',
    },
    failed: {
      icon: XCircle,
      color: 'text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/30',
      label: 'Failed',
    },
    partial: {
      icon: AlertCircle,
      color: 'text-amber-600 dark:text-amber-400 bg-amber-100 dark:bg-amber-900/30',
      label: 'Partial',
    },
  }

  const { icon: Icon, color, label } = config[verdict]

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${color}`}>
      <Icon size={14} />
      {label}
    </span>
  )
}

// =============================================================================
// Acceptance Results Component
// =============================================================================

function AcceptanceResults({ run }: { run: AgentRun }) {
  const results = run.acceptance_results as Record<string, { passed: boolean; message: string }> | null

  if (!results || Object.keys(results).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-neo-text-secondary">
        <Clock size={32} className="mb-2 opacity-50" />
        <p>No acceptance results yet</p>
        <p className="text-xs mt-1">Results will appear after validation runs</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {Object.entries(results).map(([name, result]) => (
        <div
          key={name}
          className={`
            neo-card-flat p-3
            ${result.passed ? 'border-l-4 border-l-green-500' : 'border-l-4 border-l-red-500'}
          `}
        >
          <div className="flex items-start gap-2">
            {result.passed ? (
              <CheckCircle size={16} className="text-green-600 dark:text-green-400 mt-0.5" />
            ) : (
              <XCircle size={16} className="text-red-600 dark:text-red-400 mt-0.5" />
            )}
            <div className="flex-1 min-w-0">
              <p className="font-medium text-sm">{name}</p>
              <p className="text-xs text-neo-text-secondary mt-1">{result.message}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// =============================================================================
// API Response Types (for runId mode)
// =============================================================================

interface AgentRunDetailResponse {
  id: string
  agent_spec_id: string
  status: AgentRunStatus
  started_at: string | null
  completed_at: string | null
  turns_used: number
  tokens_in: number
  tokens_out: number
  final_verdict: AgentRunVerdict | null
  acceptance_results: Record<string, { passed: boolean; message: string }> | null
  error: string | null
  retry_count: number
  spec?: {
    id: string
    name: string
    display_name: string
    icon: string | null
    task_type: string
    max_turns: number
    source_feature_id: number | null
  }
}

// =============================================================================
// Data Fetching Hook (for runId mode)
// =============================================================================

function useRunDetails(runId: string | undefined, isOpen: boolean) {
  const [data, setData] = useState<DynamicAgentData | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!runId || !isOpen) {
      return
    }

    let cancelled = false

    async function fetchRunDetails() {
      setIsLoading(true)
      setError(null)

      try {
        const response = await fetch(`/api/agent-runs/${runId}`)
        if (!response.ok) {
          if (response.status === 404) {
            throw new Error('Run not found')
          }
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || `HTTP ${response.status}`)
        }

        const runData: AgentRunDetailResponse = await response.json()

        if (cancelled) return

        // Convert API response to DynamicAgentData format
        const agentRun: AgentRun = {
          id: runData.id,
          agent_spec_id: runData.agent_spec_id,
          status: runData.status,
          started_at: runData.started_at,
          completed_at: runData.completed_at,
          turns_used: runData.turns_used,
          tokens_in: runData.tokens_in,
          tokens_out: runData.tokens_out,
          final_verdict: runData.final_verdict,
          acceptance_results: runData.acceptance_results,
          error: runData.error,
          retry_count: runData.retry_count,
        }

        // Use spec from response or create a minimal spec
        const spec: AgentSpecSummary = runData.spec
          ? {
              id: runData.spec.id,
              name: runData.spec.name,
              display_name: runData.spec.display_name,
              icon: runData.spec.icon,
              task_type: runData.spec.task_type as AgentSpecSummary['task_type'],
              max_turns: runData.spec.max_turns,
              source_feature_id: runData.spec.source_feature_id,
            }
          : {
              id: runData.agent_spec_id,
              name: 'Agent Run',
              display_name: 'Agent Run',
              icon: '🤖',
              task_type: 'custom',
              max_turns: 100,
              source_feature_id: null,
            }

        setData({ spec, run: agentRun })
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to fetch run details')
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    fetchRunDetails()

    return () => {
      cancelled = true
    }
  }, [runId, isOpen])

  return { data, isLoading, error }
}

// =============================================================================
// Main Component
// =============================================================================

export function RunInspector(props: RunInspectorProps) {
  const { isOpen, onClose, onPause, onResume, onCancel } = props

  // Determine mode and get data accordingly
  const isRunIdMode = 'runId' in props && props.runId !== undefined
  const fetchedData = useRunDetails(isRunIdMode ? props.runId : undefined, isOpen)

  // In data mode, use provided data; in runId mode, use fetched data
  const data = isRunIdMode ? fetchedData.data : props.data ?? null
  const isLoading = isRunIdMode ? fetchedData.isLoading : props.isLoading ?? false
  const error = isRunIdMode ? fetchedData.error : props.error ?? null

  const [activeTab, setActiveTab] = useState<TabId>('timeline')
  const [isPausing, setIsPausing] = useState(false)
  const [isResuming, setIsResuming] = useState(false)
  const [isCancelling, setIsCancelling] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  // Handle Escape key to close the panel
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  // Handle pause action with loading state
  const handlePause = useCallback(async () => {
    if (!data?.run?.id || !onPause) return
    setIsPausing(true)
    setActionError(null)
    try {
      await onPause(data.run.id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to pause')
    } finally {
      setIsPausing(false)
    }
  }, [data?.run?.id, onPause])

  // Handle resume action with loading state
  const handleResume = useCallback(async () => {
    if (!data?.run?.id || !onResume) return
    setIsResuming(true)
    setActionError(null)
    try {
      await onResume(data.run.id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to resume')
    } finally {
      setIsResuming(false)
    }
  }, [data?.run?.id, onResume])

  // Handle cancel action with loading state
  const handleCancel = useCallback(async () => {
    if (!data?.run?.id || !onCancel) return
    setIsCancelling(true)
    setActionError(null)
    try {
      await onCancel(data.run.id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to cancel')
    } finally {
      setIsCancelling(false)
    }
  }, [data?.run?.id, onCancel])

  if (!isOpen) return null

  const status: AgentRunStatus = data?.run?.status ?? 'pending'
  const canPause = status === 'running' && onPause
  const canResume = status === 'paused' && onResume
  const canCancel = (status === 'running' || status === 'paused') && onCancel

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-labelledby="run-inspector-title"
    >
      {/* Backdrop - click to close */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel - slides in from the right */}
      <div
        className="
          relative w-full sm:w-[90%] md:w-[70%] lg:max-w-lg
          bg-neo-card border-l-4 border-neo-border
          shadow-neo-left-lg flex flex-col h-full
          animate-slide-in-right
        "
      >
        {/* Loading state */}
        {isLoading && (
          <RunInspectorSkeleton className="p-4" />
        )}

        {/* Error state */}
        {!isLoading && error && (
          <div className="flex flex-col items-center justify-center h-full p-8">
            <AlertCircle className="w-12 h-12 text-neo-danger mb-4" />
            <p className="text-lg font-bold mb-2">Failed to load</p>
            <p className="text-sm text-neo-text-secondary mb-4">{error}</p>
            <button className="neo-btn neo-btn-sm" onClick={onClose}>
              Close
            </button>
          </div>
        )}

        {/* Content */}
        {!isLoading && !error && data && (
          <>
            {/* Header */}
            <div className="p-4 border-b border-neo-border">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-2xl" role="img" aria-hidden="true">
                    {data.spec.icon || '🤖'}
                  </span>
                  <div className="min-w-0">
                    <h2
                      id="run-inspector-title"
                      className="font-display font-bold text-lg truncate"
                    >
                      {data.spec.display_name}
                    </h2>
                    <p className="text-xs text-neo-text-secondary font-mono truncate">
                      {data.spec.name}
                    </p>
                  </div>
                </div>
                <button
                  className="neo-btn neo-btn-sm neo-btn-icon flex-shrink-0"
                  onClick={onClose}
                  aria-label="Close inspector (Escape)"
                  title="Close (Esc)"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Status and verdict */}
              {data.run && (
                <div className="flex items-center gap-3 mt-3 flex-wrap">
                  <StatusBadge status={status} />
                  <VerdictBadge verdict={data.run.final_verdict} />
                  {data.run.started_at && (
                    <span className="text-xs text-neo-text-muted">
                      Started: {new Date(data.run.started_at).toLocaleString()}
                    </span>
                  )}
                </div>
              )}

              {/* Progress bar */}
              {data.run && (
                <TurnsProgressBar
                  used={data.run.turns_used}
                  max={data.spec.max_turns}
                  status={status}
                  className="mt-3"
                />
              )}

              {/* Error message */}
              {data.run?.error && (
                <div className="mt-3 p-2 rounded text-xs bg-[var(--color-status-failed-bg)] text-[var(--color-status-failed-text)]">
                  <p className="font-medium">Error:</p>
                  <p className="mt-1">{data.run.error}</p>
                </div>
              )}
            </div>

            {/* Tabs */}
            <div className="flex border-b border-neo-border" role="tablist">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  className={`
                    flex-1 py-3 text-sm font-medium transition-colors
                    ${activeTab === tab.id
                      ? 'text-neo-accent border-b-2 border-neo-accent'
                      : 'text-neo-text-secondary hover:text-neo-text'
                    }
                  `}
                  onClick={() => setActiveTab(tab.id)}
                  aria-selected={activeTab === tab.id}
                  role="tab"
                  id={`tab-${tab.id}`}
                  aria-controls={`panel-${tab.id}`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto p-4">
              {activeTab === 'timeline' && data.run && (
                <div
                  role="tabpanel"
                  id="panel-timeline"
                  aria-labelledby="tab-timeline"
                >
                  <EventTimeline
                    runId={data.run.id}
                    pageSize={25}
                    autoScroll={status === 'running'}
                  />
                </div>
              )}
              {activeTab === 'timeline' && !data.run && (
                <div
                  role="tabpanel"
                  id="panel-timeline"
                  aria-labelledby="tab-timeline"
                  className="flex flex-col items-center justify-center h-64 text-neo-text-secondary"
                >
                  <Clock size={32} className="mb-2 opacity-50" />
                  <p>No run started yet</p>
                </div>
              )}
              {activeTab === 'artifacts' && data.run && (
                <div
                  role="tabpanel"
                  id="panel-artifacts"
                  aria-labelledby="tab-artifacts"
                >
                  <ArtifactList runId={data.run.id} />
                </div>
              )}
              {activeTab === 'artifacts' && !data.run && (
                <div
                  role="tabpanel"
                  id="panel-artifacts"
                  aria-labelledby="tab-artifacts"
                  className="flex flex-col items-center justify-center h-64 text-neo-text-secondary"
                >
                  <Clock size={32} className="mb-2 opacity-50" />
                  <p>No artifacts yet</p>
                </div>
              )}
              {activeTab === 'acceptance' && data.run && (
                <div
                  role="tabpanel"
                  id="panel-acceptance"
                  aria-labelledby="tab-acceptance"
                >
                  <AcceptanceResults run={data.run} />
                </div>
              )}
              {activeTab === 'acceptance' && !data.run && (
                <div
                  role="tabpanel"
                  id="panel-acceptance"
                  aria-labelledby="tab-acceptance"
                  className="flex flex-col items-center justify-center h-64 text-neo-text-secondary"
                >
                  <Clock size={32} className="mb-2 opacity-50" />
                  <p>No acceptance results yet</p>
                </div>
              )}
            </div>

            {/* Footer with actions */}
            {data.run && (canPause || canResume || canCancel) && (
              <div className="p-4 border-t border-neo-border">
                {/* Action error */}
                {actionError && (
                  <div className="mb-3 p-2 rounded text-xs bg-[var(--color-status-failed-bg)] text-[var(--color-status-failed-text)]">
                    {actionError}
                  </div>
                )}

                <div className="flex justify-end gap-2 flex-wrap">
                  {canPause && (
                    <LoadingButton
                      isLoading={isPausing}
                      loadingText="Pausing..."
                      variant="warning"
                      size="sm"
                      icon={<Pause size={14} />}
                      onClick={handlePause}
                      title="Pause execution"
                    >
                      Pause
                    </LoadingButton>
                  )}
                  {canResume && (
                    <LoadingButton
                      isLoading={isResuming}
                      loadingText="Resuming..."
                      variant="success"
                      size="sm"
                      icon={<Play size={14} />}
                      onClick={handleResume}
                      title="Resume execution"
                    >
                      Resume
                    </LoadingButton>
                  )}
                  {canCancel && (
                    <LoadingButton
                      isLoading={isCancelling}
                      loadingText="Cancelling..."
                      variant="danger"
                      size="sm"
                      icon={<Square size={14} />}
                      onClick={handleCancel}
                      title="Cancel execution"
                    >
                      Cancel
                    </LoadingButton>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default RunInspector
