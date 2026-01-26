/**
 * TurnsProgressBar Component
 * ==========================
 *
 * A reusable progress bar component showing turns_used / max_turns
 * with animation and status-appropriate coloring.
 *
 * Features:
 * - Animated width transition on update
 * - Tooltip with exact values on hover
 * - Status-appropriate color coding (uses Feature #65 status colors)
 * - Edge case handling for max=0
 *
 * @example
 * ```tsx
 * <TurnsProgressBar used={5} max={10} status="running" />
 * ```
 */

import { useState, useRef, useEffect } from 'react'
import type { AgentRunStatus } from '../lib/types'

// ============================================================================
// Types
// ============================================================================

export interface TurnsProgressBarProps {
  /** Number of turns used (0 or greater) */
  used: number
  /** Maximum number of turns allowed (0 or greater) */
  max: number
  /** Optional status for color coding (defaults to 'pending') */
  status?: AgentRunStatus
  /** Optional custom className for styling overrides */
  className?: string
  /** Whether to show the text label above the bar */
  showLabel?: boolean
  /** Custom label text (defaults to "Turns") */
  label?: string
  /** Size variant of the progress bar */
  size?: 'sm' | 'md' | 'lg'
}

// ============================================================================
// Tooltip Component
// ============================================================================

interface TooltipProps {
  used: number
  max: number
  percentage: number
  visible: boolean
  position: { x: number; y: number }
}

function ProgressTooltip({ used, max, percentage, visible, position }: TooltipProps) {
  if (!visible) return null

  return (
    <div
      className="neo-tooltip fixed pointer-events-none z-50 whitespace-nowrap"
      style={{
        left: position.x,
        top: position.y,
        transform: 'translate(-50%, -100%)',
        marginTop: '-8px',
      }}
      role="tooltip"
    >
      <div className="flex flex-col items-center gap-0.5">
        <span className="font-bold">{used} / {max} turns</span>
        <span className="text-neo-text-secondary text-[10px]">
          {percentage.toFixed(1)}% complete
        </span>
      </div>
    </div>
  )
}

// ============================================================================
// Size Configurations
// ============================================================================

const sizeConfig = {
  sm: {
    height: 'h-1.5',
    barClass: '',
    fontSize: 'text-[10px]',
  },
  md: {
    height: 'h-2',
    barClass: '',
    fontSize: 'text-xs',
  },
  lg: {
    height: 'h-3',
    barClass: '',
    fontSize: 'text-sm',
  },
}

// ============================================================================
// Main Component
// ============================================================================

export function TurnsProgressBar({
  used,
  max,
  status = 'pending',
  className = '',
  showLabel = true,
  label = 'Turns',
  size = 'md',
}: TurnsProgressBarProps) {
  // Tooltip state
  const [showTooltip, setShowTooltip] = useState(false)
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 })
  const barRef = useRef<HTMLDivElement>(null)
  const fillRef = useRef<HTMLDivElement>(null)

  // Calculate percentage, handling edge cases
  // When max is 0, we treat it as 0% (no progress possible)
  const percentage = max > 0 ? Math.min((used / max) * 100, 100) : 0

  // Handle edge case: if used > 0 but max = 0, show warning state
  const isOverflow = max === 0 && used > 0
  const effectivePercentage = isOverflow ? 100 : percentage

  // Get size configuration
  const { height, fontSize } = sizeConfig[size]

  // Handle mouse move for tooltip positioning
  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = barRef.current?.getBoundingClientRect()
    if (rect) {
      setTooltipPosition({
        x: e.clientX,
        y: rect.top,
      })
    }
  }

  // Handle mouse enter/leave
  const handleMouseEnter = (e: React.MouseEvent) => {
    setShowTooltip(true)
    handleMouseMove(e)
  }

  const handleMouseLeave = () => {
    setShowTooltip(false)
  }

  // Animate width on percentage change
  useEffect(() => {
    if (fillRef.current) {
      // Force a reflow to ensure animation triggers
      fillRef.current.style.width = `${effectivePercentage}%`
    }
  }, [effectivePercentage])

  return (
    <div className={`${className}`}>
      {/* Label row */}
      {showLabel && (
        <div className={`flex justify-between ${fontSize} text-neo-text-secondary mb-1`}>
          <span>{label}</span>
          <span>
            {used} / {max}
          </span>
        </div>
      )}

      {/* Progress bar container */}
      <div
        ref={barRef}
        className={`neo-progress ${height} cursor-default`}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onMouseMove={handleMouseMove}
        role="progressbar"
        aria-valuenow={used}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={`${used} of ${max} turns used`}
      >
        {/* Animated fill */}
        <div
          ref={fillRef}
          className={`
            neo-progress-fill
            neo-progress-fill-${status}
            ${isOverflow ? 'neo-progress-fill-failed' : ''}
          `}
          style={{
            width: `${effectivePercentage}%`,
            transition: 'width 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)',
          }}
        />
      </div>

      {/* Tooltip */}
      <ProgressTooltip
        used={used}
        max={max}
        percentage={percentage}
        visible={showTooltip}
        position={tooltipPosition}
      />
    </div>
  )
}

// ============================================================================
// Convenience Export for DynamicAgentCard Integration
// ============================================================================

/**
 * Legacy wrapper for backward compatibility with DynamicAgentCard
 * @deprecated Use TurnsProgressBar directly with explicit props
 */
export function TurnsProgressBarLegacy({
  turnsUsed,
  maxTurns,
  status,
}: {
  turnsUsed: number
  maxTurns: number
  status: AgentRunStatus
}) {
  return (
    <TurnsProgressBar
      used={turnsUsed}
      max={maxTurns}
      status={status}
      className="mt-3"
    />
  )
}

export default TurnsProgressBar
