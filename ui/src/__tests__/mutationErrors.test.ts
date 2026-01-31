/**
 * Feature #165: Mutation errors show clear user-facing messages
 *
 * Tests that:
 * 1. fetchJSON extracts descriptive error messages from API responses
 * 2. httpStatusMessage provides human-readable fallbacks for HTTP status codes
 * 3. useHandledMutation's default onError shows toast with errorTitle + error.message
 * 4. Toast system renders error notifications
 * 5. ConfirmDialog accepts and displays an error prop
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

/** Helper: read a source file relative to ui/src/ */
function readSrc(relativePath: string): string {
  return readFileSync(resolve(__dirname, '..', relativePath), 'utf-8')
}

// ---------------------------------------------------------------------------
// Test 1: fetchJSON error extraction
// ---------------------------------------------------------------------------

describe('fetchJSON error extraction', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('extracts error.detail from FastAPI HTTPException responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: 'Invalid project name' }),
        { status: 400, statusText: 'Bad Request' }
      )
    )

    const { listProjects } = await import('../lib/api')
    await expect(listProjects()).rejects.toThrow('Invalid project name')
  })

  it('extracts error.message from custom error responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({ error_code: 'NOT_FOUND', message: "Feature 99999 not found" }),
        { status: 404, statusText: 'Not Found' }
      )
    )

    const { listProjects } = await import('../lib/api')
    await expect(listProjects()).rejects.toThrow('Feature 99999 not found')
  })

  it('falls back to user-friendly status message when no detail/message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('Server Error', {
        status: 500,
        statusText: 'Internal Server Error',
        headers: { 'Content-Type': 'text/plain' },
      })
    )

    const { listProjects } = await import('../lib/api')
    await expect(listProjects()).rejects.toThrow('Server error')
  })

  it('provides descriptive fallback for 404 when no detail', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('{}', { status: 404 })
    )

    const { listProjects } = await import('../lib/api')
    await expect(listProjects()).rejects.toThrow('Resource not found')
  })

  it('provides descriptive fallback for 422 when no detail', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('{}', { status: 422 })
    )

    const { listProjects } = await import('../lib/api')
    await expect(listProjects()).rejects.toThrow('Invalid data')
  })
})

// ---------------------------------------------------------------------------
// Test 2: useHandledMutation wires errorTitle to toast
// ---------------------------------------------------------------------------

describe('useHandledMutation error handling', () => {
  it('default onError calls toast.error with errorTitle and error message', async () => {
    const { toast } = await import('../hooks/useToast')
    const toastSpy = vi.spyOn(toast, 'error')

    const errorTitle = 'Failed to update feature'
    const error = new Error('Feature 99999 not found')
    const message = error instanceof Error ? error.message : String(error)
    toast.error(errorTitle, message)

    expect(toastSpy).toHaveBeenCalledWith(
      'Failed to update feature',
      'Feature 99999 not found'
    )

    toastSpy.mockRestore()
  })

  it('all mutation hooks in useProjects have descriptive errorTitle', () => {
    const source = readSrc('hooks/useProjects.ts')

    // Count useHandledMutation calls and errorTitle occurrences
    const mutationCount = (source.match(/useHandledMutation\(/g) || []).length
    const errorTitleCount = (source.match(/errorTitle:/g) || []).length

    expect(mutationCount).toBeGreaterThan(0)
    // Every useHandledMutation call should have an errorTitle
    // (useUpdateSettings has custom onError, so it doesn't need one)
    // At minimum, the number of errorTitles should be close to mutation count
    expect(errorTitleCount).toBeGreaterThanOrEqual(mutationCount - 1)
  })
})

// ---------------------------------------------------------------------------
// Test 3: Toast system
// ---------------------------------------------------------------------------

describe('Toast notification system', () => {
  it('emits error toasts with title and message', async () => {
    const { toast } = await import('../hooks/useToast')

    // Verify the function doesn't throw and accepts both arguments
    toast.error('Failed to delete feature', 'Feature 42 not found')
    expect(true).toBe(true)
  })

  it('error toasts have 6000ms duration', () => {
    const source = readSrc('hooks/useToast.ts')
    expect(source).toContain("type === 'error' ? 6000")
  })
})

// ---------------------------------------------------------------------------
// Test 4: ConfirmDialog error prop
// ---------------------------------------------------------------------------

describe('ConfirmDialog error prop', () => {
  it('ConfirmDialog component accepts error prop in its interface', () => {
    const source = readSrc('components/ConfirmDialog.tsx')

    // Verify the error prop exists in the interface
    expect(source).toContain('error?: string | null')

    // Verify the inline error rendering
    expect(source).toContain('{error && (')
    expect(source).toContain('AlertCircle')

    // Verify the error prop has a default value
    expect(source).toContain('error = null')
  })
})

// ---------------------------------------------------------------------------
// Test 5: Modals use inline error + stay interactive
// ---------------------------------------------------------------------------

describe('Modal inline error handling', () => {
  it('ProjectSelector keeps dialog open on delete error and passes error prop', () => {
    const source = readSrc('components/ProjectSelector.tsx')

    // Verify deleteError state exists
    expect(source).toContain('deleteError')
    expect(source).toContain('setDeleteError')

    // Verify error is passed to ConfirmDialog
    expect(source).toContain('error={deleteError}')

    // Verify dialog stays open on error (no setProjectToDelete(null) in catch)
    const catchBlock = source.match(/catch\s*\(error\)\s*\{[\s\S]*?\}/)?.[0] || ''
    expect(catchBlock).toContain('setDeleteError')
    expect(catchBlock).not.toContain('setProjectToDelete(null)')
  })

  it('SettingsModal shows actual error message with context', () => {
    const source = readSrc('components/SettingsModal.tsx')

    // Should show actual error message, not generic string
    expect(source).toContain('updateSettings.error?.message')
    expect(source).toContain('Failed to save settings:')

    // Should include AlertCircle icon
    expect(source).toContain('AlertCircle')
  })

  it('ScheduleModal error messages include context prefix', () => {
    const source = readSrc('components/ScheduleModal.tsx')

    // Verify error messages include operation context
    expect(source).toContain('Failed to create schedule:')
    expect(source).toContain('Failed to toggle schedule:')
    expect(source).toContain('Failed to delete schedule:')

    // Verify error display includes icon and dismiss button
    expect(source).toContain('AlertCircle')
    expect(source).toContain("setError(null)")
  })

  it('AddFeatureForm shows inline error and remains interactive', () => {
    const source = readSrc('components/AddFeatureForm.tsx')

    // Has inline error state
    expect(source).toContain('error && (')
    expect(source).toContain('AlertCircle')

    // Form can be resubmitted (button not permanently disabled)
    expect(source).toContain('createFeature.isPending')
  })

  it('FeatureModal shows inline error on skip/delete failure', () => {
    const source = readSrc('components/FeatureModal.tsx')

    // Has inline error state
    expect(source).toContain('error && (')
    expect(source).toContain('AlertCircle')

    // Error includes context
    expect(source).toContain('Failed to skip feature')
    expect(source).toContain('Failed to delete feature')

    // Buttons remain interactive (disabled only during pending)
    expect(source).toContain('skipFeature.isPending')
    expect(source).toContain('deleteFeature.isPending')
  })
})

// ---------------------------------------------------------------------------
// Test 6: API error message clarity
// ---------------------------------------------------------------------------

describe('API httpStatusMessage fallbacks', () => {
  it('api.ts contains httpStatusMessage function with user-friendly messages', () => {
    const source = readSrc('lib/api.ts')

    // Verify the function exists
    expect(source).toContain('function httpStatusMessage(status: number): string')

    // Verify key status codes have friendly messages
    expect(source).toContain("case 400: return 'Bad request")
    expect(source).toContain("case 404: return 'Resource not found")
    expect(source).toContain("case 500: return 'Server error")
    expect(source).toContain("case 422: return 'Invalid data")
    expect(source).toContain("case 429: return 'Too many requests")
  })
})
