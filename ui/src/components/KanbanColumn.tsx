import { useRef, useCallback } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { FeatureCard } from './FeatureCard'
import { Plus, Sparkles, Wand2 } from 'lucide-react'
import type { Feature, ActiveAgent } from '../lib/types'

interface KanbanColumnProps {
  title: string
  count: number
  features: Feature[]
  allFeatures?: Feature[]  // For dependency status calculation
  activeAgents?: ActiveAgent[]  // Active agents for showing which agent is working on a feature
  color: 'pending' | 'progress' | 'done'
  onFeatureClick: (feature: Feature) => void
  onAddFeature?: () => void
  onExpandProject?: () => void
  showExpandButton?: boolean
  onCreateSpec?: () => void  // Callback to start spec creation
  showCreateSpec?: boolean   // Show "Create Spec" button when project has no spec
}

const colorMap = {
  pending: 'var(--color-neo-pending)',
  progress: 'var(--color-neo-progress)',
  done: 'var(--color-neo-done)',
}

// Threshold above which we enable virtualization for performance
const VIRTUALIZATION_THRESHOLD = 50

// Estimated height of each feature card including gap (in pixels)
const ESTIMATED_ITEM_SIZE = 160

// Gap between items in pixels (matches space-y-3 = 0.75rem = 12px)
const ITEM_GAP = 12

function VirtualizedFeatureList({
  features,
  allFeatures,
  agentByFeatureId,
  color,
  onFeatureClick,
}: {
  features: Feature[]
  allFeatures: Feature[]
  agentByFeatureId: Map<number, ActiveAgent>
  color: 'pending' | 'progress' | 'done'
  onFeatureClick: (feature: Feature) => void
}) {
  const parentRef = useRef<HTMLDivElement>(null)

  const virtualizer = useVirtualizer({
    count: features.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ESTIMATED_ITEM_SIZE,
    overscan: 5, // Render 5 extra items above/below viewport for smooth scrolling
    gap: ITEM_GAP,
  })

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent, index: number) => {
      if (e.key === 'ArrowDown' && index < features.length - 1) {
        e.preventDefault()
        virtualizer.scrollToIndex(index + 1, { align: 'auto' })
        // Focus the next item after scroll completes
        requestAnimationFrame(() => {
          const nextEl = parentRef.current?.querySelector(
            `[data-index="${index + 1}"] button`
          ) as HTMLElement | null
          nextEl?.focus()
        })
      } else if (e.key === 'ArrowUp' && index > 0) {
        e.preventDefault()
        virtualizer.scrollToIndex(index - 1, { align: 'auto' })
        requestAnimationFrame(() => {
          const prevEl = parentRef.current?.querySelector(
            `[data-index="${index - 1}"] button`
          ) as HTMLElement | null
          prevEl?.focus()
        })
      }
    },
    [features.length, virtualizer]
  )

  return (
    <div
      ref={parentRef}
      className="p-4 max-h-[600px] overflow-y-auto bg-[var(--color-neo-bg)]"
      role="list"
      aria-label={`${color} features`}
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {virtualizer.getVirtualItems().map((virtualItem) => {
          const feature = features[virtualItem.index]
          return (
            <div
              key={feature.id}
              data-index={virtualItem.index}
              ref={virtualizer.measureElement}
              role="listitem"
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualItem.start}px)`,
              }}
              onKeyDown={(e) => handleKeyDown(e, virtualItem.index)}
            >
              <FeatureCard
                feature={feature}
                onClick={() => onFeatureClick(feature)}
                isInProgress={color === 'progress'}
                allFeatures={allFeatures}
                activeAgent={agentByFeatureId.get(feature.id)}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function KanbanColumn({
  title,
  count,
  features,
  allFeatures = [],
  activeAgents = [],
  color,
  onFeatureClick,
  onAddFeature,
  onExpandProject,
  showExpandButton,
  onCreateSpec,
  showCreateSpec,
}: KanbanColumnProps) {
  // Create a map of feature ID to active agent for quick lookup
  const agentByFeatureId = new Map(
    activeAgents.map(agent => [agent.featureId, agent])
  )

  const useVirtualization = features.length >= VIRTUALIZATION_THRESHOLD

  return (
    <div
      className="neo-card overflow-hidden"
      style={{ borderColor: colorMap[color] }}
    >
      {/* Header */}
      <div
        className="px-4 py-3 border-b-3 border-[var(--color-neo-border)]"
        style={{ backgroundColor: colorMap[color] }}
      >
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-bold uppercase flex items-center gap-2 text-[var(--color-neo-text-on-bright)]">
            {title}
            <span className="neo-badge bg-[var(--color-neo-card)] text-[var(--color-neo-text)]">{count}</span>
          </h2>
          {(onAddFeature || onExpandProject) && (
            <div className="flex items-center gap-2">
              {onAddFeature && (
                <button
                  onClick={onAddFeature}
                  className="neo-btn neo-btn-primary text-sm py-1.5 px-2"
                  title="Add new feature (N)"
                >
                  <Plus size={16} />
                </button>
              )}
              {onExpandProject && showExpandButton && (
                <button
                  onClick={onExpandProject}
                  className="neo-btn bg-[var(--color-neo-progress)] text-[var(--color-neo-text-on-bright)] text-sm py-1.5 px-2"
                  title="Expand project with AI (E)"
                >
                  <Sparkles size={16} />
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Cards - use virtualization for large lists (50+), standard rendering for small lists */}
      {features.length === 0 ? (
        <div className="p-4 bg-[var(--color-neo-bg)]">
          <div className="text-center py-8 text-[var(--color-neo-text-secondary)]">
            {showCreateSpec && onCreateSpec ? (
              <div className="space-y-4">
                <p>No spec created yet</p>
                <button
                  onClick={onCreateSpec}
                  className="neo-btn neo-btn-primary inline-flex items-center gap-2"
                >
                  <Wand2 size={18} />
                  Create Spec with AI
                </button>
              </div>
            ) : (
              'No features'
            )}
          </div>
        </div>
      ) : useVirtualization ? (
        <VirtualizedFeatureList
          features={features}
          allFeatures={allFeatures}
          agentByFeatureId={agentByFeatureId}
          color={color}
          onFeatureClick={onFeatureClick}
        />
      ) : (
        <div className="p-4 space-y-3 max-h-[600px] overflow-y-auto bg-[var(--color-neo-bg)]">
          {features.map((feature, index) => (
            <div
              key={feature.id}
              className="animate-slide-in"
              style={{ animationDelay: `${index * 50}ms` }}
            >
              <FeatureCard
                feature={feature}
                onClick={() => onFeatureClick(feature)}
                isInProgress={color === 'progress'}
                allFeatures={allFeatures}
                activeAgent={agentByFeatureId.get(feature.id)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
