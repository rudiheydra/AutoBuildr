/**
 * EventTimeline Component
 * =======================
 *
 * Displays a vertical timeline of AgentEvents for an AgentRun.
 * Used in the Run Inspector panel to show the execution history.
 *
 * Features:
 * - Vertical timeline with timestamps
 * - Different icons for each event type
 * - Expandable cards for payload details
 * - Filter dropdown by event_type
 * - Load more button for pagination
 * - Auto-scroll to latest event on update
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Play,
  Wrench,
  FileOutput,
  RotateCw,
  CheckCircle,
  XCircle,
  Pause,
  PlayCircle,
  Timer,
  ClipboardCheck,
  ChevronDown,
  ChevronUp,
  Filter,
  Loader2,
  RefreshCw,
  AlertCircle,
} from 'lucide-react'
import type { AgentEvent, AgentEventType, AgentEventListResponse } from '../lib/types'

// =============================================================================
// Props Interface
// =============================================================================

interface EventTimelineProps {
  /** The AgentRun ID to fetch events for */
  runId: string
  /** Optional callback when an event is clicked */
  onEventClick?: (event: AgentEvent) => void
  /** Optional className for container styling */
  className?: string
  /** Whether to auto-scroll to latest events (default: true) */
  autoScroll?: boolean
  /** Initial page size (default: 25) */
  pageSize?: number
}

// =============================================================================
// Event Type Configuration
// =============================================================================

interface EventTypeConfig {
  icon: typeof Play
  label: string
  color: string
  bgColor: string
}

const EVENT_TYPE_CONFIG: Record<AgentEventType, EventTypeConfig> = {
  started: {
    icon: Play,
    label: 'Started',
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
  },
  tool_call: {
    icon: Wrench,
    label: 'Tool Call',
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-100 dark:bg-blue-900/30',
  },
  tool_result: {
    icon: FileOutput,
    label: 'Tool Result',
    color: 'text-purple-600 dark:text-purple-400',
    bgColor: 'bg-purple-100 dark:bg-purple-900/30',
  },
  turn_complete: {
    icon: RotateCw,
    label: 'Turn Complete',
    color: 'text-gray-600 dark:text-gray-400',
    bgColor: 'bg-gray-100 dark:bg-gray-900/30',
  },
  acceptance_check: {
    icon: ClipboardCheck,
    label: 'Acceptance Check',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-100 dark:bg-amber-900/30',
  },
  completed: {
    icon: CheckCircle,
    label: 'Completed',
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
  },
  failed: {
    icon: XCircle,
    label: 'Failed',
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-100 dark:bg-red-900/30',
  },
  paused: {
    icon: Pause,
    label: 'Paused',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-100 dark:bg-amber-900/30',
  },
  resumed: {
    icon: PlayCircle,
    label: 'Resumed',
    color: 'text-cyan-600 dark:text-cyan-400',
    bgColor: 'bg-cyan-100 dark:bg-cyan-900/30',
  },
  timeout: {
    icon: Timer,
    label: 'Timeout',
    color: 'text-orange-600 dark:text-orange-400',
    bgColor: 'bg-orange-100 dark:bg-orange-900/30',
  },
}

// All valid event types for the filter dropdown
const ALL_EVENT_TYPES: AgentEventType[] = [
  'started',
  'tool_call',
  'tool_result',
  'turn_complete',
  'acceptance_check',
  'completed',
  'failed',
  'paused',
  'resumed',
  'timeout',
]

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Format timestamp for display
 */
function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/**
 * Format timestamp with date for tooltip
 */
function formatFullTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/**
 * Truncate long strings for preview
 */
function truncateString(str: string, maxLength: number = 100): string {
  if (str.length <= maxLength) return str
  return str.slice(0, maxLength) + '...'
}

/**
 * Format payload for display
 */
function formatPayload(payload: Record<string, unknown> | null): string {
  if (!payload) return 'No payload'
  try {
    return JSON.stringify(payload, null, 2)
  } catch {
    return 'Unable to display payload'
  }
}

// =============================================================================
// Single Event Card Component
// =============================================================================

interface EventCardProps {
  event: AgentEvent
  isExpanded: boolean
  onToggle: () => void
  onClick?: () => void
}

function EventCard({ event, isExpanded, onToggle, onClick }: EventCardProps) {
  const config = EVENT_TYPE_CONFIG[event.event_type] || EVENT_TYPE_CONFIG.started
  const Icon = config.icon

  // Build summary text based on event type
  const getSummaryText = (): string => {
    if (event.tool_name) {
      return event.tool_name
    }
    if (event.payload) {
      // Try to extract meaningful info from payload
      const payload = event.payload
      if (typeof payload.message === 'string') {
        return truncateString(payload.message, 80)
      }
      if (typeof payload.tool === 'string') {
        return payload.tool as string
      }
      if (typeof payload.error === 'string') {
        return truncateString(payload.error, 80)
      }
    }
    return config.label
  }

  return (
    <div
      className={`
        relative pl-8 pb-4 last:pb-0
        before:absolute before:left-3 before:top-0 before:bottom-0 before:w-0.5
        before:bg-neo-border/30 last:before:hidden
      `}
    >
      {/* Timeline dot with icon */}
      <div
        className={`
          absolute left-0 top-0 w-6 h-6 rounded-full flex items-center justify-center
          border-2 border-neo-border ${config.bgColor}
          transition-transform hover:scale-110
        `}
        title={config.label}
      >
        <Icon size={12} className={config.color} />
      </div>

      {/* Event card */}
      <div
        className={`
          neo-card-flat p-3 ml-2 cursor-pointer
          transition-all duration-200
          hover:translate-x-1
          ${isExpanded ? 'ring-2 ring-neo-accent/50' : ''}
        `}
        onClick={() => {
          onToggle()
          onClick?.()
        }}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onToggle()
            onClick?.()
          }
        }}
        aria-expanded={isExpanded}
        aria-label={`${config.label} event${event.tool_name ? `: ${event.tool_name}` : ''} at ${formatTimestamp(event.timestamp)}, sequence ${event.sequence}. ${isExpanded ? 'Collapse' : 'Expand'} for details.`}
      >
        {/* Header row */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span
              className={`
                neo-badge text-[10px] px-1.5 py-0.5
                ${config.bgColor} ${config.color}
              `}
            >
              {config.label}
            </span>
            <span className="text-xs text-neo-text-secondary truncate" title={getSummaryText()}>
              {getSummaryText()}
            </span>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <span
              className="text-[10px] text-neo-text-muted font-mono"
              title={formatFullTimestamp(event.timestamp)}
            >
              {formatTimestamp(event.timestamp)}
            </span>
            <span className="text-[10px] text-neo-text-muted">#{event.sequence}</span>
            {isExpanded ? (
              <ChevronUp size={14} className="text-neo-text-secondary" />
            ) : (
              <ChevronDown size={14} className="text-neo-text-secondary" />
            )}
          </div>
        </div>

        {/* Expanded payload details */}
        {isExpanded && event.payload && (
          <div className="mt-3 pt-3 border-t border-neo-border/30">
            <pre
              className="
                text-xs font-mono p-2 rounded
                bg-neo-neutral-100 dark:bg-neo-neutral-800
                overflow-x-auto max-h-60 whitespace-pre-wrap break-words
              "
            >
              {formatPayload(event.payload)}
            </pre>
            {event.payload_truncated && (
              <p className="text-xs text-neo-text-muted mt-1">
                <AlertCircle size={12} className="inline mr-1" />
                Payload truncated (original size: {event.payload_truncated} bytes)
              </p>
            )}
            {event.artifact_ref && (
              <p className="text-xs text-neo-text-secondary mt-1">
                Artifact: <code className="font-mono">{event.artifact_ref}</code>
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// Filter Dropdown Component
// =============================================================================

interface FilterDropdownProps {
  selectedType: AgentEventType | null
  onChange: (type: AgentEventType | null) => void
}

function FilterDropdown({ selectedType, onChange }: FilterDropdownProps) {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const selectedConfig = selectedType ? EVENT_TYPE_CONFIG[selectedType] : null

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        className={`
          neo-btn neo-btn-sm flex items-center gap-1.5
          ${selectedType ? 'neo-btn-primary' : ''}
        `}
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={`Filter events. Currently showing: ${selectedConfig ? selectedConfig.label : 'All Events'}`}
      >
        <Filter size={14} aria-hidden="true" />
        {selectedConfig ? selectedConfig.label : 'All Events'}
        <ChevronDown size={14} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>

      {isOpen && (
        <div
          className="absolute top-full left-0 mt-1 z-50 neo-dropdown min-w-[160px]"
          role="listbox"
          aria-label="Filter events by type"
        >
          {/* All events option */}
          <button
            className={`
              neo-dropdown-item flex items-center gap-2
              ${selectedType === null ? 'bg-neo-pending' : ''}
            `}
            onClick={() => {
              onChange(null)
              setIsOpen(false)
            }}
            role="option"
            aria-selected={selectedType === null}
          >
            All Events
          </button>

          {/* Divider */}
          <div className="border-t border-neo-border my-1" aria-hidden="true" />

          {/* Event type options */}
          {ALL_EVENT_TYPES.map((type) => {
            const config = EVENT_TYPE_CONFIG[type]
            const Icon = config.icon
            return (
              <button
                key={type}
                className={`
                  neo-dropdown-item flex items-center gap-2
                  ${selectedType === type ? 'bg-neo-pending' : ''}
                `}
                onClick={() => {
                  onChange(type)
                  setIsOpen(false)
                }}
                role="option"
                aria-selected={selectedType === type}
              >
                <Icon size={14} className={config.color} aria-hidden="true" />
                {config.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// Main EventTimeline Component
// =============================================================================

export function EventTimeline({
  runId,
  onEventClick,
  className = '',
  autoScroll = true,
  pageSize = 25,
}: EventTimelineProps) {
  // State
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filterType, setFilterType] = useState<AgentEventType | null>(null)
  const [expandedEventId, setExpandedEventId] = useState<number | null>(null)

  // Refs
  const containerRef = useRef<HTMLDivElement>(null)
  const endRef = useRef<HTMLDivElement>(null)

  // Fetch events from API
  const fetchEvents = useCallback(
    async (offset: number = 0, append: boolean = false) => {
      try {
        if (offset === 0) {
          setIsLoading(true)
        } else {
          setIsLoadingMore(true)
        }
        setError(null)

        // Build URL with query parameters
        const params = new URLSearchParams({
          limit: pageSize.toString(),
          offset: offset.toString(),
        })
        if (filterType) {
          params.append('event_type', filterType)
        }

        const response = await fetch(`/api/agent-runs/${runId}/events?${params}`)

        if (!response.ok) {
          if (response.status === 404) {
            throw new Error('Run not found')
          }
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || `HTTP ${response.status}`)
        }

        const data: AgentEventListResponse = await response.json()

        if (append) {
          setEvents((prev) => [...prev, ...data.events])
        } else {
          setEvents(data.events)
        }
        setTotal(data.total)
        setHasMore(data.has_more)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch events')
      } finally {
        setIsLoading(false)
        setIsLoadingMore(false)
      }
    },
    [runId, filterType, pageSize]
  )

  // Initial fetch and refetch on filter change
  useEffect(() => {
    setEvents([])
    setExpandedEventId(null)
    fetchEvents(0, false)
  }, [fetchEvents])

  // Auto-scroll to latest event
  useEffect(() => {
    if (autoScroll && endRef.current && events.length > 0) {
      endRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [events.length, autoScroll])

  // Handle load more
  const handleLoadMore = () => {
    if (!isLoadingMore && hasMore) {
      fetchEvents(events.length, true)
    }
  }

  // Handle refresh
  const handleRefresh = () => {
    setExpandedEventId(null)
    fetchEvents(0, false)
  }

  // Handle filter change
  const handleFilterChange = (type: AgentEventType | null) => {
    setFilterType(type)
    setExpandedEventId(null)
  }

  // Toggle event expansion
  const toggleEventExpansion = (eventId: number) => {
    setExpandedEventId((prev) => (prev === eventId ? null : eventId))
  }

  // Loading state
  if (isLoading) {
    return (
      <div className={`flex flex-col items-center justify-center p-8 ${className}`}>
        <Loader2 className="w-8 h-8 animate-spin text-neo-progress mb-2" />
        <p className="text-sm text-neo-text-secondary">Loading events...</p>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className={`flex flex-col items-center justify-center p-8 ${className}`}>
        <AlertCircle className="w-8 h-8 text-neo-danger mb-2" />
        <p className="text-sm text-neo-text-secondary mb-3">{error}</p>
        <button className="neo-btn neo-btn-sm" onClick={handleRefresh}>
          <RefreshCw size={14} />
          Retry
        </button>
      </div>
    )
  }

  // Empty state
  if (events.length === 0) {
    return (
      <div className={`flex flex-col ${className}`}>
        {/* Header with filter */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <h3 className="font-display text-sm font-bold">Event Timeline</h3>
            <span className="text-xs text-neo-text-muted">(0 events)</span>
          </div>
          <div className="flex items-center gap-2">
            <FilterDropdown selectedType={filterType} onChange={handleFilterChange} />
            <button
              className="neo-btn neo-btn-sm neo-btn-icon"
              onClick={handleRefresh}
              title="Refresh"
              aria-label="Refresh event timeline"
            >
              <RefreshCw size={14} aria-hidden="true" />
            </button>
          </div>
        </div>

        <div className="neo-empty-state">
          <p className="text-neo-text-secondary">
            {filterType
              ? `No ${EVENT_TYPE_CONFIG[filterType].label.toLowerCase()} events found`
              : 'No events recorded yet'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={`flex flex-col ${className}`} ref={containerRef}>
      {/* Header with filter and refresh */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h3 className="font-display text-sm font-bold">Event Timeline</h3>
          <span className="text-xs text-neo-text-muted">
            ({events.length} of {total})
          </span>
        </div>
        <div className="flex items-center gap-2">
          <FilterDropdown selectedType={filterType} onChange={handleFilterChange} />
          <button
            className="neo-btn neo-btn-sm neo-btn-icon"
            onClick={handleRefresh}
            title="Refresh"
            aria-label="Refresh event timeline"
            disabled={isLoading}
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Timeline */}
      <div className="flex-1 overflow-y-auto pr-2">
        <div className="relative">
          {events.map((event) => (
            <EventCard
              key={event.id}
              event={event}
              isExpanded={expandedEventId === event.id}
              onToggle={() => toggleEventExpansion(event.id)}
              onClick={() => onEventClick?.(event)}
            />
          ))}

          {/* Auto-scroll anchor */}
          <div ref={endRef} />
        </div>

        {/* Load more button */}
        {hasMore && (
          <div className="flex justify-center mt-4 mb-2">
            <button
              className="neo-btn neo-btn-sm"
              onClick={handleLoadMore}
              disabled={isLoadingMore}
            >
              {isLoadingMore ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Loading...
                </>
              ) : (
                <>
                  <ChevronDown size={14} />
                  Load More ({total - events.length} remaining)
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// Export types for use in parent components
export type { EventTimelineProps, AgentEvent, AgentEventType }
