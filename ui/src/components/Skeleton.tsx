/**
 * Skeleton Component
 * ==================
 *
 * Provides skeleton loading states for UI components.
 * Used to show loading placeholders while data is being fetched.
 *
 * Features:
 * - Multiple variants (text, circle, rect, card)
 * - Configurable width/height
 * - Pulse animation
 * - Dark mode support
 */

interface SkeletonProps {
  /** Width of the skeleton (CSS value, e.g., '100%', '200px') */
  width?: string | number
  /** Height of the skeleton (CSS value, e.g., '20px', '100%') */
  height?: string | number
  /** Border radius (CSS value or preset) */
  radius?: 'sm' | 'md' | 'lg' | 'full' | string
  /** Additional CSS classes */
  className?: string
}

/**
 * Base Skeleton component with pulse animation
 */
export function Skeleton({
  width = '100%',
  height = '1rem',
  radius = 'md',
  className = '',
}: SkeletonProps) {
  const radiusMap: Record<string, string> = {
    sm: '0.125rem',
    md: '0.25rem',
    lg: '0.5rem',
    full: '9999px',
  }

  const resolvedRadius = radiusMap[radius] || radius

  return (
    <div
      className={`animate-pulse bg-neo-neutral-200 dark:bg-neo-neutral-700 ${className}`}
      style={{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof height === 'number' ? `${height}px` : height,
        borderRadius: resolvedRadius,
      }}
      aria-hidden="true"
    />
  )
}

/**
 * Skeleton for text content (single line)
 */
export function SkeletonText({
  width = '100%',
  className = '',
}: {
  width?: string | number
  className?: string
}) {
  return <Skeleton width={width} height="1rem" radius="md" className={className} />
}

/**
 * Skeleton for circular elements (avatars, icons)
 */
export function SkeletonCircle({
  size = 40,
  className = '',
}: {
  size?: number
  className?: string
}) {
  return <Skeleton width={size} height={size} radius="full" className={className} />
}

/**
 * Skeleton for rectangular elements (images, cards)
 */
export function SkeletonRect({
  width = '100%',
  height = 100,
  className = '',
}: {
  width?: string | number
  height?: number
  className?: string
}) {
  return <Skeleton width={width} height={height} radius="md" className={className} />
}

/**
 * Skeleton for DynamicAgentCard
 * Matches the layout of the actual card component
 */
export function DynamicAgentCardSkeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={`neo-card p-4 ${className}`}
      aria-label="Loading agent card..."
      aria-busy="true"
    >
      {/* Header with icon and name */}
      <div className="flex items-start gap-3 mb-3">
        {/* Icon placeholder */}
        <SkeletonCircle size={32} />
        <div className="flex-1 min-w-0">
          {/* Display name */}
          <SkeletonText width="80%" className="mb-1" />
          {/* Machine name */}
          <SkeletonText width="60%" className="h-3" />
        </div>
      </div>

      {/* Status badge */}
      <div className="mb-2">
        <Skeleton width={80} height={24} radius="md" />
      </div>

      {/* Progress bar */}
      <div className="mt-3">
        <div className="flex justify-between mb-1">
          <SkeletonText width={40} className="h-3" />
          <SkeletonText width={50} className="h-3" />
        </div>
        <Skeleton width="100%" height={8} radius="sm" />
      </div>

      {/* Token usage */}
      <div className="mt-2 flex justify-between">
        <SkeletonText width={60} className="h-3" />
        <SkeletonText width={60} className="h-3" />
      </div>

      {/* Feature link */}
      <div className="mt-2 pt-2 border-t border-neo-border/30">
        <SkeletonText width={80} className="h-3" />
      </div>
    </div>
  )
}

/**
 * Skeleton for EventTimeline event cards
 */
export function EventCardSkeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={`relative pl-8 pb-4 ${className}`}
      aria-hidden="true"
    >
      {/* Timeline dot */}
      <div className="absolute left-0 top-0">
        <SkeletonCircle size={24} />
      </div>

      {/* Event card */}
      <div className="neo-card-flat p-3 ml-2">
        {/* Header row */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-1">
            {/* Event type badge */}
            <Skeleton width={60} height={18} radius="md" />
            {/* Summary text */}
            <SkeletonText width="60%" className="h-3" />
          </div>
          <div className="flex items-center gap-2">
            {/* Timestamp */}
            <SkeletonText width={60} className="h-2.5" />
            {/* Sequence number */}
            <SkeletonText width={30} className="h-2.5" />
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * Skeleton for EventTimeline with multiple events
 */
export function EventTimelineSkeleton({
  eventCount = 5,
  className = '',
}: {
  eventCount?: number
  className?: string
}) {
  return (
    <div className={`flex flex-col ${className}`} aria-label="Loading events..." aria-busy="true">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <SkeletonText width={100} className="h-4" />
          <SkeletonText width={60} className="h-3" />
        </div>
        <div className="flex items-center gap-2">
          <Skeleton width={100} height={32} radius="md" />
          <Skeleton width={32} height={32} radius="md" />
        </div>
      </div>

      {/* Event list */}
      <div className="flex-1 overflow-hidden">
        {Array.from({ length: eventCount }).map((_, i) => (
          <EventCardSkeleton key={i} />
        ))}
      </div>
    </div>
  )
}

/**
 * Skeleton for ArtifactList artifact cards
 */
export function ArtifactCardSkeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`neo-card-flat p-3 ${className}`} aria-hidden="true">
      <div className="flex items-start gap-3">
        {/* Icon */}
        <Skeleton width={40} height={40} radius="lg" />

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Header row */}
          <div className="flex items-center gap-2 mb-1">
            <Skeleton width={70} height={16} radius="md" />
            <SkeletonText width={80} className="h-2.5" />
          </div>
          {/* Path */}
          <SkeletonText width="90%" className="h-3.5 mb-1" />
          {/* Metadata */}
          <div className="flex items-center gap-3">
            <SkeletonText width={50} className="h-3" />
            <SkeletonText width={80} className="h-3" />
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1">
          <Skeleton width={32} height={32} radius="md" />
          <Skeleton width={32} height={32} radius="md" />
        </div>
      </div>
    </div>
  )
}

/**
 * Skeleton for ArtifactList with multiple artifacts
 */
export function ArtifactListSkeleton({
  artifactCount = 3,
  className = '',
}: {
  artifactCount?: number
  className?: string
}) {
  return (
    <div className={`flex flex-col ${className}`} aria-label="Loading artifacts..." aria-busy="true">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <SkeletonText width={70} className="h-4" />
          <SkeletonText width={60} className="h-3" />
        </div>
        <div className="flex items-center gap-2">
          <Skeleton width={100} height={32} radius="md" />
          <Skeleton width={32} height={32} radius="md" />
        </div>
      </div>

      {/* Artifact list */}
      <div className="flex-1 overflow-hidden space-y-2">
        {Array.from({ length: artifactCount }).map((_, i) => (
          <ArtifactCardSkeleton key={i} />
        ))}
      </div>
    </div>
  )
}

/**
 * Skeleton for Run Inspector panel
 */
export function RunInspectorSkeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={`flex flex-col h-full ${className}`}
      aria-label="Loading run inspector..."
      aria-busy="true"
    >
      {/* Header */}
      <div className="p-4 border-b border-neo-border">
        <div className="flex items-center gap-3 mb-2">
          <SkeletonCircle size={32} />
          <div className="flex-1">
            <SkeletonText width="60%" className="h-5 mb-1" />
            <SkeletonText width="40%" className="h-3" />
          </div>
        </div>
        <div className="flex items-center gap-2 mt-3">
          <Skeleton width={80} height={28} radius="md" />
          <SkeletonText width={100} className="h-3" />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-neo-border">
        <Skeleton width={80} height={40} radius="sm" className="mx-1" />
        <Skeleton width={80} height={40} radius="sm" className="mx-1" />
        <Skeleton width={80} height={40} radius="sm" className="mx-1" />
      </div>

      {/* Content */}
      <div className="flex-1 p-4 overflow-hidden">
        <EventTimelineSkeleton eventCount={4} />
      </div>

      {/* Footer with actions */}
      <div className="p-4 border-t border-neo-border flex justify-end gap-2">
        <Skeleton width={80} height={36} radius="md" />
        <Skeleton width={80} height={36} radius="md" />
      </div>
    </div>
  )
}

// Named exports are defined above with 'export function'
