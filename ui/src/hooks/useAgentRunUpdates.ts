/**
 * useAgentRunUpdates Hook
 * =======================
 *
 * Feature #71: Real-time Card Updates via WebSocket
 *
 * This hook connects DynamicAgentCard components to WebSocket for real-time
 * status, progress, and event updates for a specific AgentRun.
 *
 * Features:
 * - Subscribe to run-specific WebSocket events
 * - Handle agent_run_started, agent_event_logged, agent_acceptance_update messages
 * - Update component state on message receipt
 * - Automatic unsubscribe on unmount
 * - Graceful reconnection handling
 *
 * Usage:
 *   const { run, turnsUsed, acceptanceResults, lastEvent } = useAgentRunUpdates({
 *     projectName: 'my-project',
 *     runId: 'abc-123-...',
 *     initialRun: initialRunData,
 *   })
 */

import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import type {
  AgentRun,
  AgentRunStatus,
  AgentRunVerdict,
  WSMessage,
  WSAgentRunStartedMessage,
  WSAgentEventLoggedMessage,
  WSAgentAcceptanceUpdateMessage,
  AgentEventType,
} from '../lib/types'

/**
 * Options for the useAgentRunUpdates hook
 */
export interface UseAgentRunUpdatesOptions {
  /** Project name for WebSocket connection */
  projectName: string | null
  /** Run ID to subscribe to (null = don't subscribe) */
  runId: string | null
  /** Initial run data (optional, for pre-populated state) */
  initialRun?: AgentRun | null
  /** Whether to enable the WebSocket connection (default: true) */
  enabled?: boolean
}

/**
 * State returned by the useAgentRunUpdates hook
 */
export interface AgentRunUpdateState {
  /** Current run status */
  status: AgentRunStatus | null
  /** Number of turns used (updated in real-time) */
  turnsUsed: number
  /** Tokens consumed (input) */
  tokensIn: number
  /** Tokens produced (output) */
  tokensOut: number
  /** Final verdict after acceptance check */
  finalVerdict: AgentRunVerdict | null
  /** Per-validator acceptance results */
  acceptanceResults: Record<string, { passed: boolean; message: string }> | null
  /** Error message if failed */
  error: string | null
  /** Last event received */
  lastEvent: {
    type: AgentEventType
    sequence: number
    toolName?: string
    timestamp: string
  } | null
  /** Whether we're connected to WebSocket */
  isConnected: boolean
  /** Whether we're currently reconnecting */
  isReconnecting: boolean
}

/**
 * Return type of the useAgentRunUpdates hook
 */
export interface UseAgentRunUpdatesReturn extends AgentRunUpdateState {
  /** Manually refresh by resetting to initial state */
  reset: () => void
}

// Reconnection configuration
const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 15000, 30000] // Exponential backoff with cap

/**
 * Extract initial state from an AgentRun object
 */
function getInitialState(initialRun?: AgentRun | null): AgentRunUpdateState {
  if (!initialRun) {
    return {
      status: null,
      turnsUsed: 0,
      tokensIn: 0,
      tokensOut: 0,
      finalVerdict: null,
      acceptanceResults: null,
      error: null,
      lastEvent: null,
      isConnected: false,
      isReconnecting: false,
    }
  }

  return {
    status: initialRun.status,
    turnsUsed: initialRun.turns_used,
    tokensIn: initialRun.tokens_in,
    tokensOut: initialRun.tokens_out,
    finalVerdict: initialRun.final_verdict,
    acceptanceResults: initialRun.acceptance_results,
    error: initialRun.error,
    lastEvent: null,
    isConnected: false,
    isReconnecting: false,
  }
}

/**
 * Hook for real-time AgentRun updates via WebSocket.
 *
 * Subscribes to WebSocket events for a specific run and updates state
 * when agent_event_logged, agent_acceptance_update, or agent_run_started
 * messages are received.
 */
export function useAgentRunUpdates(options: UseAgentRunUpdatesOptions): UseAgentRunUpdatesReturn {
  const { projectName, runId, initialRun, enabled = true } = options

  // State
  const [state, setState] = useState<AgentRunUpdateState>(() => getInitialState(initialRun))

  // Refs for WebSocket management
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptRef = useRef(0)
  const mountedRef = useRef(true)

  // Memoize the run filter for message filtering
  const shouldProcessMessage = useMemo(() => {
    if (!runId) return () => false
    return (messageRunId: string) => messageRunId === runId
  }, [runId])

  /**
   * Handle agent_run_started message
   */
  const handleRunStarted = useCallback((message: WSAgentRunStartedMessage) => {
    if (!shouldProcessMessage(message.run_id)) return

    setState(prev => ({
      ...prev,
      status: 'running',
    }))
  }, [shouldProcessMessage])

  /**
   * Handle agent_event_logged message
   * Updates turns_used based on turn_complete events
   */
  const handleEventLogged = useCallback((message: WSAgentEventLoggedMessage) => {
    if (!shouldProcessMessage(message.run_id)) return

    setState(prev => {
      const updates: Partial<AgentRunUpdateState> = {
        lastEvent: {
          type: message.event_type,
          sequence: message.sequence,
          toolName: message.tool_name,
          timestamp: message.timestamp,
        },
      }

      // Update turns_used when turn_complete event is received
      // Each turn_complete event represents exactly one completed turn,
      // so we increment the count rather than using a sequence-based heuristic.
      if (message.event_type === 'turn_complete') {
        updates.turnsUsed = prev.turnsUsed + 1
      }

      return { ...prev, ...updates }
    })
  }, [shouldProcessMessage])

  /**
   * Handle agent_acceptance_update message
   * Updates acceptance results and final verdict
   *
   * Feature #160: Now uses canonical acceptance_results Record from backend
   * instead of manually converting validator_results array.
   */
  const handleAcceptanceUpdate = useCallback((message: WSAgentAcceptanceUpdateMessage) => {
    if (!shouldProcessMessage(message.run_id)) return

    setState(prev => {
      // Feature #160: Use canonical acceptance_results directly from backend
      // The backend now emits the same Record<string, AcceptanceValidatorResult>
      // format on both REST API and WebSocket, eliminating UI normalization.
      const acceptanceResults = message.acceptance_results ?? null

      // Determine status based on verdict
      let status: AgentRunStatus | null = prev.status
      if (message.final_verdict === 'passed') {
        status = 'completed'
      } else if (message.final_verdict === 'failed') {
        status = 'failed'
      }

      return {
        ...prev,
        finalVerdict: message.final_verdict,
        acceptanceResults,
        status,
      }
    })
  }, [shouldProcessMessage])

  /**
   * Process incoming WebSocket messages
   */
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const message: WSMessage = JSON.parse(event.data)

      switch (message.type) {
        case 'agent_run_started':
          handleRunStarted(message as WSAgentRunStartedMessage)
          break
        case 'agent_event_logged':
          handleEventLogged(message as WSAgentEventLoggedMessage)
          break
        case 'agent_acceptance_update':
          handleAcceptanceUpdate(message as WSAgentAcceptanceUpdateMessage)
          break
        case 'pong':
          // Heartbeat response - no action needed
          break
        default:
          // Ignore other message types
          break
      }
    } catch {
      console.error('[useAgentRunUpdates] Failed to parse WebSocket message')
    }
  }, [handleRunStarted, handleEventLogged, handleAcceptanceUpdate])

  /**
   * Connect to WebSocket
   */
  const connect = useCallback(() => {
    if (!projectName || !enabled || !mountedRef.current) return

    // Build WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/ws/projects/${encodeURIComponent(projectName)}`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        if (!mountedRef.current) {
          ws.close()
          return
        }

        reconnectAttemptRef.current = 0
        setState(prev => ({
          ...prev,
          isConnected: true,
          isReconnecting: false,
        }))
      }

      ws.onmessage = handleMessage

      ws.onclose = () => {
        if (!mountedRef.current) return

        wsRef.current = null
        setState(prev => ({
          ...prev,
          isConnected: false,
        }))

        // Attempt reconnection with exponential backoff
        if (enabled) {
          const delay = RECONNECT_DELAYS[Math.min(reconnectAttemptRef.current, RECONNECT_DELAYS.length - 1)]
          reconnectAttemptRef.current++

          setState(prev => ({ ...prev, isReconnecting: true }))

          reconnectTimeoutRef.current = setTimeout(() => {
            if (mountedRef.current) {
              connect()
            }
          }, delay)
        }
      }

      ws.onerror = () => {
        // Close will trigger reconnection
        ws.close()
      }
    } catch {
      console.error('[useAgentRunUpdates] Failed to create WebSocket connection')
    }
  }, [projectName, enabled, handleMessage])

  /**
   * Reset state to initial values
   */
  const reset = useCallback(() => {
    setState(getInitialState(initialRun))
  }, [initialRun])

  /**
   * Send ping to keep connection alive
   */
  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'ping' }))
    }
  }, [])

  // Effect: Update state when initialRun changes
  useEffect(() => {
    if (initialRun) {
      setState(prev => ({
        ...prev,
        status: initialRun.status,
        turnsUsed: initialRun.turns_used,
        tokensIn: initialRun.tokens_in,
        tokensOut: initialRun.tokens_out,
        finalVerdict: initialRun.final_verdict,
        acceptanceResults: initialRun.acceptance_results,
        error: initialRun.error,
      }))
    }
  }, [initialRun])

  // Effect: Connect to WebSocket when project/run changes
  useEffect(() => {
    mountedRef.current = true

    if (!projectName || !runId || !enabled) {
      // Disconnect if no project/run or disabled
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      return
    }

    connect()

    // Set up ping interval to keep connection alive
    const pingInterval = setInterval(sendPing, 30000)

    return () => {
      mountedRef.current = false
      clearInterval(pingInterval)

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }

      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [projectName, runId, enabled, connect, sendPing])

  return {
    ...state,
    reset,
  }
}

/**
 * Simplified hook for subscribing to updates for multiple runs.
 * Returns a Map of run_id -> update state.
 */
export function useMultipleAgentRunUpdates(
  projectName: string | null,
  runIds: string[],
  enabled: boolean = true
): Map<string, AgentRunUpdateState> {
  const [stateMap, setStateMap] = useState<Map<string, AgentRunUpdateState>>(new Map())

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptRef = useRef(0)
  const mountedRef = useRef(true)

  // Create a Set for O(1) lookup
  const runIdSet = useMemo(() => new Set(runIds), [runIds])

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const message: WSMessage = JSON.parse(event.data)
      let runId: string | null = null

      // Extract run_id from message
      if (message.type === 'agent_run_started') {
        runId = (message as WSAgentRunStartedMessage).run_id
      } else if (message.type === 'agent_event_logged') {
        runId = (message as WSAgentEventLoggedMessage).run_id
      } else if (message.type === 'agent_acceptance_update') {
        runId = (message as WSAgentAcceptanceUpdateMessage).run_id
      }

      if (!runId || !runIdSet.has(runId)) return

      setStateMap(prev => {
        const newMap = new Map(prev)
        const currentState = newMap.get(runId!) || getInitialState(null)

        if (message.type === 'agent_run_started') {
          newMap.set(runId!, {
            ...currentState,
            status: 'running',
            isConnected: true,
          })
        } else if (message.type === 'agent_event_logged') {
          const eventMsg = message as WSAgentEventLoggedMessage
          const updates: Partial<AgentRunUpdateState> = {
            lastEvent: {
              type: eventMsg.event_type,
              sequence: eventMsg.sequence,
              toolName: eventMsg.tool_name,
              timestamp: eventMsg.timestamp,
            },
          }

          if (eventMsg.event_type === 'turn_complete') {
            updates.turnsUsed = currentState.turnsUsed + 1
          }

          newMap.set(runId!, { ...currentState, ...updates })
        } else if (message.type === 'agent_acceptance_update') {
          // Feature #160: Use canonical acceptance_results Record from backend
          const acceptMsg = message as WSAgentAcceptanceUpdateMessage
          const acceptanceResults = acceptMsg.acceptance_results ?? null

          let status: AgentRunStatus | null = currentState.status
          if (acceptMsg.final_verdict === 'passed') {
            status = 'completed'
          } else if (acceptMsg.final_verdict === 'failed') {
            status = 'failed'
          }

          newMap.set(runId!, {
            ...currentState,
            finalVerdict: acceptMsg.final_verdict,
            acceptanceResults,
            status,
          })
        }

        return newMap
      })
    } catch {
      console.error('[useMultipleAgentRunUpdates] Failed to parse WebSocket message')
    }
  }, [runIdSet])

  const connect = useCallback(() => {
    if (!projectName || !enabled || !mountedRef.current) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/ws/projects/${encodeURIComponent(projectName)}`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        if (!mountedRef.current) {
          ws.close()
          return
        }
        reconnectAttemptRef.current = 0
      }

      ws.onmessage = handleMessage

      ws.onclose = () => {
        if (!mountedRef.current) return
        wsRef.current = null

        if (enabled) {
          const delay = RECONNECT_DELAYS[Math.min(reconnectAttemptRef.current, RECONNECT_DELAYS.length - 1)]
          reconnectAttemptRef.current++

          reconnectTimeoutRef.current = setTimeout(() => {
            if (mountedRef.current) {
              connect()
            }
          }, delay)
        }
      }

      ws.onerror = () => {
        ws.close()
      }
    } catch {
      console.error('[useMultipleAgentRunUpdates] Failed to create WebSocket connection')
    }
  }, [projectName, enabled, handleMessage])

  useEffect(() => {
    mountedRef.current = true

    if (!projectName || runIds.length === 0 || !enabled) {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      return
    }

    connect()

    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)

    return () => {
      mountedRef.current = false
      clearInterval(pingInterval)

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }

      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [projectName, runIds, enabled, connect])

  return stateMap
}

export default useAgentRunUpdates
