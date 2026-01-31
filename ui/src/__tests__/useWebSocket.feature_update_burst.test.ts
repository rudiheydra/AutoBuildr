/**
 * Feature #173: Virtualized list handles WebSocket update bursts without jank
 *
 * Tests that when multiple feature_update WebSocket messages arrive in rapid
 * succession (burst), the useProjectWebSocket hook debounces invalidateQueries
 * calls to prevent UI jank and redundant API fetches.
 *
 * The debounce window is 150ms — updates are coalesced and flushed once
 * after the burst settles.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useProjectWebSocket } from '../hooks/useWebSocket'

// ---------------------------------------------------------------------------
// Mock WebSocket
// ---------------------------------------------------------------------------

/** Minimal fake WebSocket that lets us dispatch messages from tests. */
class MockWebSocket {
  static instances: MockWebSocket[] = []

  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null

  readyState = WebSocket.OPEN
  url: string

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
    // Auto-connect on next tick so the hook's onopen fires
    setTimeout(() => {
      if (this.onopen) {
        this.onopen(new Event('open'))
      }
    }, 0)
  }

  send(_data: string) {
    // no-op for tests
  }

  close() {
    this.readyState = WebSocket.CLOSED
  }

  /** Helper: simulate receiving a message from the server */
  simulateMessage(data: Record<string, unknown>) {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }))
    }
  }

  static reset() {
    MockWebSocket.instances = []
  }

  static get latest(): MockWebSocket | undefined {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1]
  }
}

// Replace global WebSocket with mock
const OriginalWebSocket = globalThis.WebSocket
beforeEach(() => {
  MockWebSocket.reset()
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  globalThis.WebSocket = MockWebSocket as any
})
afterEach(() => {
  globalThis.WebSocket = OriginalWebSocket
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    )
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Feature #173: WebSocket burst debouncing', () => {
  let queryClient: QueryClient
  let invalidateSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    queryClient = createTestQueryClient()
    invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
  })

  afterEach(() => {
    queryClient.clear()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('coalesces 20+ rapid feature_update messages into a single invalidation batch', async () => {
    const projectName = 'burst-test-project'

    const { unmount } = renderHook(
      () => useProjectWebSocket(projectName),
      { wrapper: createWrapper(queryClient) },
    )

    // Allow WebSocket to connect
    await act(async () => {
      vi.advanceTimersByTime(10)
    })

    const ws = MockWebSocket.latest!
    expect(ws).toBeDefined()

    // Simulate a burst of 25 feature_update messages in quick succession
    act(() => {
      for (let i = 1; i <= 25; i++) {
        ws.simulateMessage({
          type: 'feature_update',
          feature_id: i,
          passes: true,
        })
      }
    })

    // Right after the burst, invalidateQueries should NOT have been called yet
    // (the debounce timer hasn't fired)
    expect(invalidateSpy).not.toHaveBeenCalled()

    // Advance past the 150ms debounce window
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    // Now invalidateQueries should have been called:
    // - Once for ['features', projectName]
    // - Once for ['dependencyGraph', projectName]
    // - Once for each unique feature_id (25 unique IDs)
    // Total: 2 + 25 = 27 calls, but all in ONE batch after debounce
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['features', projectName] }),
      )
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['dependencyGraph', projectName] }),
      )
    })

    // Verify it was exactly 27 calls (2 shared + 25 specific feature IDs)
    expect(invalidateSpy).toHaveBeenCalledTimes(27)

    // Verify specific feature invalidations
    for (let i = 1; i <= 25; i++) {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['feature', projectName, i] }),
      )
    }

    unmount()
  })

  it('deduplicates repeated feature_id values during a burst', async () => {
    const projectName = 'dedup-project'

    const { unmount } = renderHook(
      () => useProjectWebSocket(projectName),
      { wrapper: createWrapper(queryClient) },
    )

    await act(async () => {
      vi.advanceTimersByTime(10)
    })

    const ws = MockWebSocket.latest!

    // Send 10 updates for the same feature_id (simulating rapid polling on one feature)
    act(() => {
      for (let i = 0; i < 10; i++) {
        ws.simulateMessage({
          type: 'feature_update',
          feature_id: 42,
          passes: i % 2 === 0, // alternating
        })
      }
    })

    // No calls yet (debounced)
    expect(invalidateSpy).not.toHaveBeenCalled()

    // Advance past debounce
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    // Should only have 3 invalidations:
    // 1 for features list, 1 for dependency graph, 1 for feature 42
    // (feature_id 42 deduplicated to a single invalidation)
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledTimes(3)
    })

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['features', projectName] }),
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['dependencyGraph', projectName] }),
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['feature', projectName, 42] }),
    )

    unmount()
  })

  it('does not fire invalidation before the debounce window completes', async () => {
    const projectName = 'timing-project'

    const { unmount } = renderHook(
      () => useProjectWebSocket(projectName),
      { wrapper: createWrapper(queryClient) },
    )

    await act(async () => {
      vi.advanceTimersByTime(10)
    })

    const ws = MockWebSocket.latest!

    // Send first burst
    act(() => {
      ws.simulateMessage({ type: 'feature_update', feature_id: 1, passes: true })
    })

    // Advance only 100ms (less than 150ms debounce)
    await act(async () => {
      vi.advanceTimersByTime(100)
    })

    // Still should not have fired
    expect(invalidateSpy).not.toHaveBeenCalled()

    // Send another message (resets the debounce timer)
    act(() => {
      ws.simulateMessage({ type: 'feature_update', feature_id: 2, passes: true })
    })

    // Advance another 100ms (200ms since first, but only 100ms since last)
    await act(async () => {
      vi.advanceTimersByTime(100)
    })

    // Still debounced, should not fire yet
    expect(invalidateSpy).not.toHaveBeenCalled()

    // Advance the remaining 50ms to trigger flush
    await act(async () => {
      vi.advanceTimersByTime(60)
    })

    // Now it should have fired with both feature IDs coalesced
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledTimes(4) // features, depGraph, feature 1, feature 2
    })

    unmount()
  })

  it('handles feature_update messages without feature_id gracefully', async () => {
    const projectName = 'no-fid-project'

    const { unmount } = renderHook(
      () => useProjectWebSocket(projectName),
      { wrapper: createWrapper(queryClient) },
    )

    await act(async () => {
      vi.advanceTimersByTime(10)
    })

    const ws = MockWebSocket.latest!

    // Send feature_update without feature_id (feature_id = 0 which is falsy)
    act(() => {
      ws.simulateMessage({ type: 'feature_update', feature_id: 0, passes: true })
      ws.simulateMessage({ type: 'feature_update', feature_id: 0, passes: false })
    })

    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    // Should only invalidate the two shared queries (features list + dep graph)
    // No specific feature invalidation since feature_id was falsy
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledTimes(2)
    })

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['features', projectName] }),
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['dependencyGraph', projectName] }),
    )

    unmount()
  })

  it('allows a second burst after the first flush completes', async () => {
    const projectName = 'multi-burst-project'

    const { unmount } = renderHook(
      () => useProjectWebSocket(projectName),
      { wrapper: createWrapper(queryClient) },
    )

    await act(async () => {
      vi.advanceTimersByTime(10)
    })

    const ws = MockWebSocket.latest!

    // First burst: 5 updates
    act(() => {
      for (let i = 1; i <= 5; i++) {
        ws.simulateMessage({ type: 'feature_update', feature_id: i, passes: true })
      }
    })

    // Flush first burst
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledTimes(7) // 2 shared + 5 specific
    })

    // Clear spy to count second burst separately
    invalidateSpy.mockClear()

    // Second burst: 3 updates with different feature IDs
    act(() => {
      for (let i = 100; i <= 102; i++) {
        ws.simulateMessage({ type: 'feature_update', feature_id: i, passes: false })
      }
    })

    // Flush second burst
    await act(async () => {
      vi.advanceTimersByTime(200)
    })

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledTimes(5) // 2 shared + 3 specific
    })

    unmount()
  })
})
