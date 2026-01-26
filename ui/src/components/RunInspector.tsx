/**
 * RunInspector Component
 * ======================
 *
 * A slide-out panel for inspecting AgentRun details.
 * Shows event timeline, artifacts, and acceptance results.
 *
 * Features:
 * - Tabbed interface (Events, Artifacts, Acceptance)
 * - Loading states with skeletons
 * - Action buttons (pause, cancel) with loading spinners
 * - Optimistic updates with error revert
 * - Accessible with keyboard navigation
 */

import { useState, useCallback } from 'react'
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
import type { DynamicAgentData, AgentRunStatus, AgentRunVerdict } from '../lib/types'

// =============================================================================
// Props Interface
// =============================================================================

interface RunInspectorProps {
  /** The spec and run data to display */
  data: DynamicAgentData | null
  /** Whether the panel is open */
  isOpen: boolean
  /** Callback to close the panel */
  onClose: () => void
  /** Whether data is loading */
  isLoading?: boolean
  /** Error message if loading failed */
  error?: string | null
  /** Callback for pause action */
  onPause?: (runId: string) => Promise<void>
  /** Callback for resume action */
  onResume?: (runId: string) => Promise<void>
  /** Callback for cancel action */
  onCancel?: (runId: string) => Promise<void>
}

// =============================================================================
// Tab Types
// =============================================================================

type TabId = 'events' | 'artifacts' | 'acceptance'

interface TabConfig {
  id: TabId
  label: string
}

const TABS: TabConfig[] = [
  { id: 'events', label: 'Events' },
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

function AcceptanceResults({ run }: { run: NonNullable<DynamicAgentData['run']> }) {
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
// Main Component
// =============================================================================

export function RunInspector({
  data,
  isOpen,
  onClose,
  isLoading = false,
  error = null,
  onPause,
  onResume,
  onCancel,
}: RunInspectorProps) {
  const [activeTab, setActiveTab] = useState<TabId>('events')
  const [isPausing, setIsPausing] = useState(false)
  const [isResuming, setIsResuming] = useState(false)
  const [isCancelling, setIsCancelling] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

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
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        className="
          relative w-full max-w-lg bg-neo-card border-l-4 border-neo-border
          shadow-neo-left-lg flex flex-col h-full
          animate-slide-in-left
        "
      >
        {/* Loading state */}
        {isLoading && <RunInspectorSkeleton className="p-4" />}

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
                  <div>
                    <h2
                      id="run-inspector-title"
                      className="font-display font-bold text-lg"
                    >
                      {data.spec.display_name}
                    </h2>
                    <p className="text-xs text-neo-text-secondary font-mono">
                      {data.spec.name}
                    </p>
                  </div>
                </div>
                <button
                  className="neo-btn neo-btn-sm neo-btn-icon"
                  onClick={onClose}
                  aria-label="Close inspector"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Status and verdict */}
              {data.run && (
                <div className="flex items-center gap-3 mt-3">
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
            <div className="flex border-b border-neo-border">
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
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto p-4">
              {activeTab === 'events' && data.run && (
                <EventTimeline
                  runId={data.run.id}
                  pageSize={25}
                  autoScroll={status === 'running'}
                />
              )}
              {activeTab === 'events' && !data.run && (
                <div className="flex flex-col items-center justify-center h-64 text-neo-text-secondary">
                  <Clock size={32} className="mb-2 opacity-50" />
                  <p>No run started yet</p>
                </div>
              )}
              {activeTab === 'artifacts' && data.run && (
                <ArtifactList runId={data.run.id} />
              )}
              {activeTab === 'artifacts' && !data.run && (
                <div className="flex flex-col items-center justify-center h-64 text-neo-text-secondary">
                  <Clock size={32} className="mb-2 opacity-50" />
                  <p>No artifacts yet</p>
                </div>
              )}
              {activeTab === 'acceptance' && data.run && (
                <AcceptanceResults run={data.run} />
              )}
              {activeTab === 'acceptance' && !data.run && (
                <div className="flex flex-col items-center justify-center h-64 text-neo-text-secondary">
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

                <div className="flex justify-end gap-2">
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
