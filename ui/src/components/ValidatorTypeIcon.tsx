/**
 * ValidatorTypeIcon Component
 * ===========================
 *
 * Displays an icon for a validator type used in acceptance results.
 * Feature #74: Validator Type Icons
 *
 * Features:
 * - Icon based on validator type (test_pass, file_exists, etc.)
 * - Optional label display
 * - Tooltip with description
 * - Accessible with ARIA labels
 * - Customizable size
 */

import { getValidatorIconConfig, type ValidatorIconConfig } from '../lib/validatorIcons'

interface ValidatorTypeIconProps {
  /** The validator type string (e.g., 'test_pass', 'file_exists') */
  validatorType: string | undefined
  /** Icon size in pixels (default: 14) */
  size?: number
  /** Whether to show the label alongside the icon */
  showLabel?: boolean
  /** Additional CSS classes */
  className?: string
  /** Whether to show tooltip on hover */
  showTooltip?: boolean
}

/**
 * ValidatorTypeIcon Component
 *
 * Renders the appropriate icon for a validator type.
 * Used in AcceptanceResults component (Step 7) and
 * ValidatorStatusIndicators on card (Step 8).
 */
export function ValidatorTypeIcon({
  validatorType,
  size = 14,
  showLabel = false,
  className = '',
  showTooltip = true,
}: ValidatorTypeIconProps) {
  const config: ValidatorIconConfig = getValidatorIconConfig(validatorType)
  const Icon = config.icon

  return (
    <span
      className={`inline-flex items-center gap-1 ${className}`}
      title={showTooltip ? config.description : undefined}
      data-testid="validator-type-icon"
      data-validator-type={validatorType || 'unknown'}
    >
      <Icon
        size={size}
        aria-label={config.ariaLabel}
        aria-hidden={showLabel ? 'true' : undefined}
        className="flex-shrink-0"
      />
      {showLabel && (
        <span className="text-xs">{config.label}</span>
      )}
    </span>
  )
}

/**
 * ValidatorTypeBadge Component
 *
 * A badge-style display of validator type with icon.
 * Used for more prominent display of validator type.
 */
export function ValidatorTypeBadge({
  validatorType,
  size = 12,
  className = '',
}: Omit<ValidatorTypeIconProps, 'showLabel' | 'showTooltip'>) {
  const config: ValidatorIconConfig = getValidatorIconConfig(validatorType)
  const Icon = config.icon

  return (
    <span
      className={`
        inline-flex items-center gap-1 px-1.5 py-0.5 rounded
        bg-neo-bg-muted text-neo-text-secondary text-[10px] font-medium
        ${className}
      `}
      title={config.description}
      data-testid="validator-type-badge"
      data-validator-type={validatorType || 'unknown'}
    >
      <Icon size={size} aria-hidden="true" className="flex-shrink-0" />
      <span>{config.label}</span>
    </span>
  )
}

export default ValidatorTypeIcon
