/**
 * useResponsiveColumns Hook
 * =========================
 *
 * Provides responsive column count for grid layouts based on screen width.
 * Works with CSS breakpoints defined in globals.css for .neo-agent-card-grid.
 *
 * Breakpoints:
 * - Mobile (<640px): 1 column
 * - Tablet (640px-1023px): 2 columns
 * - Desktop (1024px-1279px): 3 columns
 * - Large Desktop (>=1280px): 4 columns
 *
 * Part of Feature #82: Mobile Responsive Agent Card Grid
 */

import { useState, useEffect } from 'react'

/**
 * Breakpoint configuration matching CSS breakpoints
 */
export const RESPONSIVE_BREAKPOINTS = {
  sm: 640,   // Tablet: 2 columns
  lg: 1024,  // Desktop: 3 columns
  xl: 1280,  // Large Desktop: 4 columns
} as const

/**
 * Column counts at each breakpoint
 */
export const COLUMN_COUNTS = {
  mobile: 1,   // < 640px
  tablet: 2,   // >= 640px
  desktop: 3,  // >= 1024px
  large: 4,    // >= 1280px
} as const

/**
 * Get column count based on window width
 */
function getColumnCount(width: number): number {
  if (width >= RESPONSIVE_BREAKPOINTS.xl) {
    return COLUMN_COUNTS.large
  }
  if (width >= RESPONSIVE_BREAKPOINTS.lg) {
    return COLUMN_COUNTS.desktop
  }
  if (width >= RESPONSIVE_BREAKPOINTS.sm) {
    return COLUMN_COUNTS.tablet
  }
  return COLUMN_COUNTS.mobile
}

/**
 * Get device type based on window width
 */
type DeviceType = 'mobile' | 'tablet' | 'desktop' | 'large'

function getDeviceType(width: number): DeviceType {
  if (width >= RESPONSIVE_BREAKPOINTS.xl) {
    return 'large'
  }
  if (width >= RESPONSIVE_BREAKPOINTS.lg) {
    return 'desktop'
  }
  if (width >= RESPONSIVE_BREAKPOINTS.sm) {
    return 'tablet'
  }
  return 'mobile'
}

/**
 * Hook return type
 */
export interface ResponsiveColumnsResult {
  /** Current number of columns for the grid */
  columns: number
  /** Current device type based on breakpoints */
  deviceType: DeviceType
  /** Whether the current device is mobile (<640px) */
  isMobile: boolean
  /** Whether the current device is tablet (640px-1023px) */
  isTablet: boolean
  /** Whether the current device is desktop (>=1024px) */
  isDesktop: boolean
  /** Whether touch interactions should be prioritized */
  isTouchDevice: boolean
  /** Current window width (for custom calculations) */
  windowWidth: number
}

/**
 * Custom hook for responsive column count detection
 *
 * Uses window resize listener with debouncing for performance.
 * Falls back to SSR-safe defaults (mobile-first: 1 column).
 *
 * @returns Responsive column information and device type
 *
 * @example
 * ```tsx
 * const { columns, isMobile } = useResponsiveColumns();
 *
 * // Use with grid navigation hook
 * const { getCardProps } = useAgentCardGridNavigation(cards.length, { columns });
 *
 * // Adjust padding for mobile
 * const cardPadding = isMobile ? 'p-5' : 'p-4';
 * ```
 */
export function useResponsiveColumns(): ResponsiveColumnsResult {
  // SSR-safe initial state (mobile-first)
  const [windowWidth, setWindowWidth] = useState(() => {
    if (typeof window !== 'undefined') {
      return window.innerWidth
    }
    return RESPONSIVE_BREAKPOINTS.sm - 1 // Default to mobile
  })

  // Detect touch device
  const [isTouchDevice, setIsTouchDevice] = useState(false)

  // Update window width on resize with debounce
  useEffect(() => {
    if (typeof window === 'undefined') return

    // Update initial width
    setWindowWidth(window.innerWidth)

    // Detect touch capability
    setIsTouchDevice(
      'ontouchstart' in window ||
      navigator.maxTouchPoints > 0 ||
      (window.matchMedia && window.matchMedia('(pointer: coarse)').matches)
    )

    // Debounced resize handler
    let timeoutId: ReturnType<typeof setTimeout>

    const handleResize = () => {
      clearTimeout(timeoutId)
      timeoutId = setTimeout(() => {
        setWindowWidth(window.innerWidth)
      }, 100) // 100ms debounce
    }

    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      clearTimeout(timeoutId)
    }
  }, [])

  // Calculate derived values
  const columns = getColumnCount(windowWidth)
  const deviceType = getDeviceType(windowWidth)
  const isMobile = deviceType === 'mobile'
  const isTablet = deviceType === 'tablet'
  const isDesktop = deviceType === 'desktop' || deviceType === 'large'

  return {
    columns,
    deviceType,
    isMobile,
    isTablet,
    isDesktop,
    isTouchDevice,
    windowWidth,
  }
}

/**
 * Simpler hook that just returns column count
 * Use this when you only need the column count for grid navigation
 */
export function useGridColumns(): number {
  const { columns } = useResponsiveColumns()
  return columns
}

export default useResponsiveColumns
