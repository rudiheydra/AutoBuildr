/**
 * useAgentIcon Hook
 * =================
 *
 * Feature #220: UI displays agent icons in agent cards
 *
 * This hook fetches and caches agent icons from the API.
 * Icons are fetched on-demand and cached in browser memory to prevent
 * redundant API calls.
 *
 * Features:
 * - Fetch icon from /api/projects/{project}/agent-specs/{specId}/icon
 * - In-memory caching with automatic deduplication
 * - Loading state while icon fetches
 * - Fallback to emoji icon if API fails
 * - HTTP caching via browser (Cache-Control headers from API)
 *
 * Usage:
 *   const { iconUrl, isLoading, error, fallbackEmoji } = useAgentIcon({
 *     projectName: 'my-project',
 *     specId: 'abc-123-...',
 *     displayName: 'Auth Login Impl',
 *     taskType: 'coding',
 *   })
 */

import { useEffect, useState, useCallback, useRef } from 'react'

/**
 * Task type to emoji fallback mapping
 */
const TASK_TYPE_EMOJI: Record<string, string> = {
  coding: '\u{1F4BB}',      // 💻
  testing: '\u{1F9EA}',     // 🧪
  refactoring: '\u{1F527}', // 🔧
  documentation: '\u{1F4DD}', // 📝
  audit: '\u{1F50D}',       // 🔍
  custom: '\u{2699}',       // ⚙️
}

const DEFAULT_EMOJI = '\u{1F916}'  // 🤖

/**
 * In-memory icon cache
 * Maps specId -> data URL or "loading" or "error"
 */
const iconCache = new Map<string, string | 'loading' | 'error'>()

/**
 * Pending fetch promises to deduplicate concurrent requests
 */
const pendingFetches = new Map<string, Promise<string>>()

/**
 * Options for the useAgentIcon hook
 */
export interface UseAgentIconOptions {
  /** Project name for API path */
  projectName: string | null
  /** AgentSpec ID to fetch icon for */
  specId: string | null
  /** Display name for fallback initial */
  displayName?: string
  /** Task type for fallback emoji */
  taskType?: string
  /** Whether to enable fetching (default: true) */
  enabled?: boolean
}

/**
 * Return type of the useAgentIcon hook
 */
export interface UseAgentIconReturn {
  /** Data URL for the icon (SVG as data URL), null if not loaded */
  iconUrl: string | null
  /** Whether the icon is currently loading */
  isLoading: boolean
  /** Error message if fetch failed */
  error: string | null
  /** Fallback emoji to show if icon fails to load */
  fallbackEmoji: string
  /** Refetch the icon (clears cache for this specId) */
  refetch: () => void
}

/**
 * Get fallback emoji based on task type
 */
function getFallbackEmoji(taskType?: string): string {
  if (!taskType) return DEFAULT_EMOJI
  return TASK_TYPE_EMOJI[taskType] || DEFAULT_EMOJI
}

/**
 * Fetch icon from API and return as data URL
 */
async function fetchIconAsDataUrl(
  projectName: string,
  specId: string
): Promise<string> {
  const cacheKey = `${projectName}:${specId}`

  // Check if there's already a pending fetch for this icon
  const pendingFetch = pendingFetches.get(cacheKey)
  if (pendingFetch) {
    return pendingFetch
  }

  // Create the fetch promise
  const fetchPromise = (async () => {
    const response = await fetch(
      `/api/projects/${encodeURIComponent(projectName)}/agent-specs/${encodeURIComponent(specId)}/icon`,
      {
        headers: {
          'Accept': 'image/svg+xml',
        },
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to fetch icon: ${response.status}`)
    }

    // Read SVG content
    const svgText = await response.text()

    // Convert to data URL for easy use in img src
    const dataUrl = `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svgText)))}`

    // Store in cache
    iconCache.set(cacheKey, dataUrl)

    return dataUrl
  })()

  // Store pending fetch
  pendingFetches.set(cacheKey, fetchPromise)

  try {
    const result = await fetchPromise
    return result
  } finally {
    // Clean up pending fetch
    pendingFetches.delete(cacheKey)
  }
}

/**
 * Hook to fetch and cache agent icons
 */
export function useAgentIcon({
  projectName,
  specId,
  displayName: _displayName,
  taskType,
  enabled = true,
}: UseAgentIconOptions): UseAgentIconReturn {
  // _displayName reserved for future use (e.g., generating initials for placeholder)
  const [iconUrl, setIconUrl] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Track if component is mounted
  const mountedRef = useRef(true)

  // Get fallback emoji
  const fallbackEmoji = getFallbackEmoji(taskType)

  // Refetch function - clears cache and re-fetches
  const refetch = useCallback(() => {
    if (!projectName || !specId) return

    const cacheKey = `${projectName}:${specId}`
    iconCache.delete(cacheKey)
    setIconUrl(null)
    setError(null)
    setIsLoading(true)

    fetchIconAsDataUrl(projectName, specId)
      .then((url) => {
        if (mountedRef.current) {
          setIconUrl(url)
          setIsLoading(false)
        }
      })
      .catch((err) => {
        if (mountedRef.current) {
          setError(err.message || 'Failed to load icon')
          setIsLoading(false)
          iconCache.set(cacheKey, 'error')
        }
      })
  }, [projectName, specId])

  // Fetch icon on mount or when dependencies change
  useEffect(() => {
    mountedRef.current = true

    if (!enabled || !projectName || !specId) {
      setIconUrl(null)
      setIsLoading(false)
      setError(null)
      return
    }

    const cacheKey = `${projectName}:${specId}`

    // Check cache first
    const cached = iconCache.get(cacheKey)
    if (cached === 'error') {
      // Previously failed - don't retry automatically
      setError('Icon load failed')
      setIsLoading(false)
      return
    }
    if (cached && cached !== 'loading') {
      // Cache hit - use cached data URL
      setIconUrl(cached)
      setIsLoading(false)
      setError(null)
      return
    }

    // Mark as loading
    iconCache.set(cacheKey, 'loading')
    setIsLoading(true)
    setError(null)

    // Fetch icon
    fetchIconAsDataUrl(projectName, specId)
      .then((url) => {
        if (mountedRef.current) {
          setIconUrl(url)
          setIsLoading(false)
        }
      })
      .catch((err) => {
        if (mountedRef.current) {
          setError(err.message || 'Failed to load icon')
          setIsLoading(false)
          iconCache.set(cacheKey, 'error')
        }
      })

    return () => {
      mountedRef.current = false
    }
  }, [projectName, specId, enabled])

  return {
    iconUrl,
    isLoading,
    error,
    fallbackEmoji,
    refetch,
  }
}

/**
 * Clear all cached icons (useful for testing)
 */
export function clearIconCache(): void {
  iconCache.clear()
}

/**
 * Get cached icon if available (for SSR/testing)
 */
export function getCachedIcon(projectName: string, specId: string): string | null {
  const cacheKey = `${projectName}:${specId}`
  const cached = iconCache.get(cacheKey)
  if (cached && cached !== 'loading' && cached !== 'error') {
    return cached
  }
  return null
}
