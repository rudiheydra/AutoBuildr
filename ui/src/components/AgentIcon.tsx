/**
 * AgentIcon Component
 * ===================
 *
 * Feature #220: UI displays agent icons in agent cards
 *
 * Displays an agent's icon fetched from the API, with loading state and
 * fallback to emoji if the API fails.
 *
 * Features:
 * - Step 1: Fetches icon from API
 * - Step 2: Displays icon in card header
 * - Step 3: Loading state while icon fetches
 * - Step 4: Fallback to emoji icon if API fails
 * - Step 5: Icon cached in browser (via useAgentIcon hook)
 */

import { useAgentIcon } from '../hooks/useAgentIcon'

/**
 * Size configurations for different icon sizes
 */
const SIZES = {
  sm: { icon: 24, emoji: 'text-lg', loading: 20 },
  md: { icon: 32, emoji: 'text-2xl', loading: 24 },
  lg: { icon: 48, emoji: 'text-4xl', loading: 32 },
} as const

export interface AgentIconProps {
  /** Project name for API path */
  projectName: string | null
  /** AgentSpec ID to fetch icon for */
  specId: string | null
  /** Display name for accessibility */
  displayName?: string
  /** Task type for fallback emoji */
  taskType?: string
  /** Icon size */
  size?: 'sm' | 'md' | 'lg'
  /** Additional CSS classes */
  className?: string
  /** Show emoji fallback during loading (default: false) */
  showEmojiWhileLoading?: boolean
}

/**
 * Loading spinner component for icon loading state
 */
function LoadingSpinner({ size }: { size: number }) {
  return (
    <div
      className="animate-spin rounded-full border-2 border-neo-border border-t-neo-progress"
      style={{
        width: size,
        height: size,
      }}
      role="status"
      aria-label="Loading icon"
    />
  )
}

/**
 * AgentIcon - Displays agent icon from API with fallback
 */
export function AgentIcon({
  projectName,
  specId,
  displayName = 'Agent',
  taskType = 'custom',
  size = 'md',
  className = '',
  showEmojiWhileLoading = false,
}: AgentIconProps) {
  const { iconUrl, isLoading, error, fallbackEmoji } = useAgentIcon({
    projectName,
    specId,
    displayName,
    taskType,
    enabled: Boolean(projectName && specId),
  })

  const sizeConfig = SIZES[size]

  // Determine what to render
  const shouldShowLoading = isLoading && !showEmojiWhileLoading
  const shouldShowEmoji = (!iconUrl || error) && (!isLoading || showEmojiWhileLoading)
  const shouldShowIcon = iconUrl && !error

  return (
    <div
      className={`flex items-center justify-center ${className}`}
      style={{
        width: sizeConfig.icon,
        height: sizeConfig.icon,
        minWidth: sizeConfig.icon,
      }}
      title={displayName}
    >
      {/* Step 3: Loading state */}
      {shouldShowLoading && (
        <LoadingSpinner size={sizeConfig.loading} />
      )}

      {/* Step 4: Fallback emoji */}
      {shouldShowEmoji && (
        <span
          className={`${sizeConfig.emoji} select-none`}
          role="img"
          aria-label={`${displayName} icon`}
        >
          {fallbackEmoji}
        </span>
      )}

      {/* Step 2: Icon from API */}
      {shouldShowIcon && (
        <img
          src={iconUrl}
          alt={`${displayName} icon`}
          width={sizeConfig.icon}
          height={sizeConfig.icon}
          className="object-contain"
          loading="lazy"
          // Use inline event handlers to handle load errors gracefully
          onError={(e) => {
            // Hide the broken image and let the parent component handle fallback
            const target = e.target as HTMLImageElement
            target.style.display = 'none'
          }}
        />
      )}
    </div>
  )
}

/**
 * AgentIconWithFallback - Convenience wrapper that always shows emoji during loading
 */
export function AgentIconWithFallback(props: Omit<AgentIconProps, 'showEmojiWhileLoading'>) {
  return <AgentIcon {...props} showEmojiWhileLoading={true} />
}

export default AgentIcon
