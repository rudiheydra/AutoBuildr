/**
 * useAgentCardGridNavigation Hook
 * ================================
 *
 * Provides keyboard navigation for a grid of DynamicAgentCards.
 * Implements arrow key navigation, focus management, and screen reader announcements.
 *
 * Features:
 * - Arrow key navigation (up/down/left/right)
 * - Home/End keys for first/last card
 * - Focus trapping within grid
 * - Screen reader announcements for navigation
 * - Configurable columns for responsive layouts
 *
 * Part of Feature #80: Keyboard Navigation for Agent Cards
 */

import { useCallback, useRef, useEffect, useState } from 'react'
import type { AgentRunStatus } from '../lib/types'

/**
 * Configuration options for the grid navigation hook
 */
export interface GridNavigationOptions {
  /** Number of columns in the grid (for arrow key calculation) */
  columns?: number
  /** Whether to wrap around at grid edges */
  wrapAround?: boolean
  /** Callback when a card is selected (Enter/Space) */
  onSelect?: (index: number) => void
  /** Callback when focus changes */
  onFocusChange?: (index: number) => void
  /** Whether navigation is enabled */
  enabled?: boolean
}

/**
 * Return type for the useAgentCardGridNavigation hook
 */
export interface GridNavigationResult {
  /** Ref to attach to the grid container */
  containerRef: React.RefObject<HTMLDivElement>
  /** Current focused card index (-1 if none) */
  focusedIndex: number
  /** Set the focused index programmatically */
  setFocusedIndex: (index: number) => void
  /** Get props to spread on each card */
  getCardProps: (index: number) => CardNavigationProps
  /** Announce a message to screen readers */
  announce: (message: string) => void
  /** Handle status change announcement */
  announceStatusChange: (cardName: string, oldStatus: AgentRunStatus, newStatus: AgentRunStatus) => void
}

/**
 * Props returned by getCardProps to spread on each card
 */
export interface CardNavigationProps {
  tabIndex: number
  'aria-selected': boolean
  'data-card-index': number
  onKeyDown: (e: React.KeyboardEvent) => void
  onFocus: () => void
  ref: (el: HTMLElement | null) => void
}

/**
 * Status labels for screen reader announcements
 */
const STATUS_LABELS: Record<AgentRunStatus, string> = {
  pending: 'pending',
  running: 'now running',
  paused: 'paused',
  completed: 'completed successfully',
  failed: 'failed',
  timeout: 'timed out',
}

/**
 * Custom hook for keyboard navigation in DynamicAgentCard grids
 *
 * @param itemCount - Total number of cards in the grid
 * @param options - Configuration options
 * @returns Grid navigation utilities
 *
 * @example
 * ```tsx
 * const { containerRef, getCardProps, announce } = useAgentCardGridNavigation(
 *   cards.length,
 *   { columns: 3, onSelect: (i) => openInspector(cards[i]) }
 * );
 *
 * return (
 *   <div ref={containerRef} role="grid">
 *     {cards.map((card, i) => (
 *       <DynamicAgentCard {...getCardProps(i)} data={card} />
 *     ))}
 *   </div>
 * );
 * ```
 */
export function useAgentCardGridNavigation(
  itemCount: number,
  options: GridNavigationOptions = {}
): GridNavigationResult {
  const {
    columns = 3,
    wrapAround = true,
    onSelect,
    onFocusChange,
    enabled = true,
  } = options

  // Track focused card index
  const [focusedIndex, setFocusedIndexState] = useState(-1)

  // Container ref for focus management
  const containerRef = useRef<HTMLDivElement>(null)

  // Refs for individual card elements
  const cardRefs = useRef<Map<number, HTMLElement>>(new Map())

  // Screen reader announcement region ref
  const announcerRef = useRef<HTMLDivElement | null>(null)

  // Create the announcer element on mount
  useEffect(() => {
    if (!announcerRef.current) {
      const announcer = document.createElement('div')
      announcer.setAttribute('role', 'status')
      announcer.setAttribute('aria-live', 'polite')
      announcer.setAttribute('aria-atomic', 'true')
      announcer.className = 'sr-only'
      announcer.style.cssText = `
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border: 0;
      `
      document.body.appendChild(announcer)
      announcerRef.current = announcer
    }

    return () => {
      if (announcerRef.current) {
        document.body.removeChild(announcerRef.current)
        announcerRef.current = null
      }
    }
  }, [])

  /**
   * Announce a message to screen readers via aria-live region
   */
  const announce = useCallback((message: string) => {
    if (announcerRef.current) {
      // Clear first to ensure announcement even if same message
      announcerRef.current.textContent = ''
      // Use requestAnimationFrame to ensure the clear is processed
      requestAnimationFrame(() => {
        if (announcerRef.current) {
          announcerRef.current.textContent = message
        }
      })
    }
  }, [])

  /**
   * Announce status changes for screen readers
   */
  const announceStatusChange = useCallback((
    cardName: string,
    oldStatus: AgentRunStatus,
    newStatus: AgentRunStatus
  ) => {
    if (oldStatus !== newStatus) {
      const statusLabel = STATUS_LABELS[newStatus] || newStatus
      announce(`${cardName} is ${statusLabel}`)
    }
  }, [announce])

  /**
   * Set focused index and trigger callback
   */
  const setFocusedIndex = useCallback((index: number) => {
    if (index >= -1 && index < itemCount) {
      setFocusedIndexState(index)
      onFocusChange?.(index)
    }
  }, [itemCount, onFocusChange])

  /**
   * Focus a card by index
   */
  const focusCard = useCallback((index: number) => {
    const card = cardRefs.current.get(index)
    if (card) {
      card.focus()
      setFocusedIndex(index)
    }
  }, [setFocusedIndex])

  /**
   * Calculate the next index based on direction
   */
  const getNextIndex = useCallback((
    currentIndex: number,
    direction: 'up' | 'down' | 'left' | 'right' | 'home' | 'end'
  ): number => {
    if (itemCount === 0) return -1

    let nextIndex = currentIndex

    switch (direction) {
      case 'left':
        nextIndex = currentIndex - 1
        break
      case 'right':
        nextIndex = currentIndex + 1
        break
      case 'up':
        nextIndex = currentIndex - columns
        break
      case 'down':
        nextIndex = currentIndex + columns
        break
      case 'home':
        return 0
      case 'end':
        return itemCount - 1
    }

    // Handle wrapping or boundary clamping
    if (wrapAround) {
      if (nextIndex < 0) {
        nextIndex = itemCount + nextIndex
      } else if (nextIndex >= itemCount) {
        nextIndex = nextIndex - itemCount
      }
    } else {
      // Clamp to valid range
      nextIndex = Math.max(0, Math.min(itemCount - 1, nextIndex))
    }

    return nextIndex
  }, [itemCount, columns, wrapAround])

  /**
   * Handle keyboard events for navigation
   */
  const handleKeyDown = useCallback((e: React.KeyboardEvent, index: number) => {
    if (!enabled) return

    let direction: 'up' | 'down' | 'left' | 'right' | 'home' | 'end' | null = null
    let shouldPreventDefault = true

    switch (e.key) {
      case 'ArrowLeft':
        direction = 'left'
        break
      case 'ArrowRight':
        direction = 'right'
        break
      case 'ArrowUp':
        direction = 'up'
        break
      case 'ArrowDown':
        direction = 'down'
        break
      case 'Home':
        direction = 'home'
        break
      case 'End':
        direction = 'end'
        break
      case 'Enter':
      case ' ':
        e.preventDefault()
        onSelect?.(index)
        return
      case 'Escape':
        // Escape is handled by the inspector component
        shouldPreventDefault = false
        break
      default:
        shouldPreventDefault = false
    }

    if (direction) {
      if (shouldPreventDefault) {
        e.preventDefault()
      }
      const nextIndex = getNextIndex(index, direction)
      if (nextIndex !== index && nextIndex >= 0) {
        focusCard(nextIndex)
      }
    }
  }, [enabled, getNextIndex, focusCard, onSelect])

  /**
   * Handle focus event on a card
   */
  const handleFocus = useCallback((index: number) => {
    setFocusedIndex(index)
  }, [setFocusedIndex])

  /**
   * Register a card element ref
   */
  const registerCard = useCallback((index: number) => (el: HTMLElement | null) => {
    if (el) {
      cardRefs.current.set(index, el)
    } else {
      cardRefs.current.delete(index)
    }
  }, [])

  /**
   * Get props to spread on each card element
   */
  const getCardProps = useCallback((index: number): CardNavigationProps => {
    const isFocused = focusedIndex === index
    // First card or focused card gets tabIndex 0 for roving tabindex pattern
    const isFirstCard = index === 0 && focusedIndex === -1

    return {
      tabIndex: isFocused || isFirstCard ? 0 : -1,
      'aria-selected': isFocused,
      'data-card-index': index,
      onKeyDown: (e: React.KeyboardEvent) => handleKeyDown(e, index),
      onFocus: () => handleFocus(index),
      ref: registerCard(index),
    }
  }, [focusedIndex, handleKeyDown, handleFocus, registerCard])

  return {
    containerRef,
    focusedIndex,
    setFocusedIndex,
    getCardProps,
    announce,
    announceStatusChange,
  }
}

export default useAgentCardGridNavigation
