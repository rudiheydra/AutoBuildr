/**
 * Feature #153: WebSocket feature_update unit test with mock WS message
 *
 * Tests that the useProjectWebSocket hook correctly invalidates React Query
 * caches when a feature_update WebSocket message is received.
 *
 * This is a unit-style test that mocks the WebSocket and QueryClient
 * to verify invalidation wiring without requiring a running backend.
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

  // Standard WebSocket callbacks
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
    // Don't fire onclose to avoid reconnection loops in tests
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

describe('useProjectWebSocket – feature_update invalidation', () => {
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

  it('invalidates ["features", projectName] on feature_update', async () => {
    const projectName = 'test-project'

    const { unmount } = renderHook(
      () => useProjectWebSocket(projectName),
      { wrapper: createWrapper(queryClient) },
    )

    // Allow WebSocket constructor setTimeout to fire (auto-connect)
    await act(async () => {
      vi.advanceTimersByTime(10)
    })

    const ws = MockWebSocket.latest!
    expect(ws).toBeDefined()

    // Simulate a feature_update message
    act(() => {
      ws.simulateMessage({
        type: 'feature_update',
        feature_id: 42,
        passes: true,
      })
    })

    // Assert invalidateQueries was called with ['features', projectName]
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          queryKey: ['features', projectName],
        }),
      )
    })

    unmount()
  })

  it('invalidates ["dependencyGraph", projectName] on feature_update', async () => {
    const projectName = 'my-app'

    const { unmount } = renderHook(
      () => useProjectWebSocket(projectName),
      { wrapper: createWrapper(queryClient) },
    )

    await act(async () => {
      vi.advanceTimersByTime(10)
    })

    const ws = MockWebSocket.latest!

    act(() => {
      ws.simulateMessage({
        type: 'feature_update',
        feature_id: 7,
        passes: false,
      })
    })

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          queryKey: ['dependencyGraph', projectName],
        }),
      )
    })

    unmount()
  })

  it('invalidates ["feature", projectName, featureId] when feature_id is present', async () => {
    const projectName = 'alpha-project'
    const featureId = 99

    const { unmount } = renderHook(
      () => useProjectWebSocket(projectName),
      { wrapper: createWrapper(queryClient) },
    )

    await act(async () => {
      vi.advanceTimersByTime(10)
    })

    const ws = MockWebSocket.latest!

    act(() => {
      ws.simulateMessage({
        type: 'feature_update',
        feature_id: featureId,
        passes: true,
      })
    })

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          queryKey: ['feature', projectName, featureId],
        }),
      )
    })

    unmount()
  })

  it('calls invalidateQueries exactly 3 times when feature_id is present', async () => {
    const projectName = 'count-project'
    const featureId = 55

    const { unmount } = renderHook(
      () => useProjectWebSocket(projectName),
      { wrapper: createWrapper(queryClient) },
    )

    await act(async () => {
      vi.advanceTimersByTime(10)
    })

    const ws = MockWebSocket.latest!

    act(() => {
      ws.simulateMessage({
        type: 'feature_update',
        feature_id: featureId,
        passes: true,
      })
    })

    await waitFor(() => {
      // Should be exactly 3: features list, dependency graph, and specific feature
      expect(invalidateSpy).toHaveBeenCalledTimes(3)
    })

    // Verify the three specific calls
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['features', projectName] }),
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['dependencyGraph', projectName] }),
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['feature', projectName, featureId] }),
    )

    unmount()
  })

  it('calls invalidateQueries only 2 times when feature_id is falsy (0)', async () => {
    const projectName = 'no-feature-id-project'

    const { unmount } = renderHook(
      () => useProjectWebSocket(projectName),
      { wrapper: createWrapper(queryClient) },
    )

    await act(async () => {
      vi.advanceTimersByTime(10)
    })

    const ws = MockWebSocket.latest!

    // feature_id = 0 is falsy, so the specific feature invalidation should NOT fire
    act(() => {
      ws.simulateMessage({
        type: 'feature_update',
        feature_id: 0,
        passes: false,
      })
    })

    await waitFor(() => {
      // Should be exactly 2: features list and dependency graph
      expect(invalidateSpy).toHaveBeenCalledTimes(2)
    })

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['features', projectName] }),
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['dependencyGraph', projectName] }),
    )
    // Should NOT have been called with a specific feature key
    expect(invalidateSpy).not.toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: expect.arrayContaining(['feature']) }),
    )

    unmount()
  })

  it('does not call invalidateQueries for non-feature_update messages', async () => {
    const projectName = 'other-msgs'

    const { unmount } = renderHook(
      () => useProjectWebSocket(projectName),
      { wrapper: createWrapper(queryClient) },
    )

    await act(async () => {
      vi.advanceTimersByTime(10)
    })

    const ws = MockWebSocket.latest!

    // Send a progress message instead of feature_update
    act(() => {
      ws.simulateMessage({
        type: 'progress',
        passing: 10,
        in_progress: 2,
        total: 50,
        percentage: 20.0,
      })
    })

    // Give it time to process
    await act(async () => {
      vi.advanceTimersByTime(50)
    })

    // invalidateQueries should NOT have been called
    expect(invalidateSpy).not.toHaveBeenCalled()

    unmount()
  })
})
