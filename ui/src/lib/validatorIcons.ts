/**
 * Validator Type Icons
 * ====================
 *
 * Icon map for different validator types used in acceptance results.
 * Feature #74: Validator Type Icons
 *
 * Validator Types:
 * - test_pass: Terminal icon - runs shell commands to test
 * - file_exists: File icon - checks if files exist
 * - lint_clean: Code icon - runs linter checks
 * - forbidden_patterns: Shield icon - security pattern checks
 * - custom: Gear/cog icon - custom validators
 */

import {
  Terminal,
  FileText,
  Code,
  Shield,
  Settings,
  HelpCircle,
  type LucideIcon,
} from 'lucide-react'

/**
 * Known validator types in the system
 */
export type ValidatorType =
  | 'test_pass'
  | 'file_exists'
  | 'lint_clean'
  | 'forbidden_patterns'
  | 'custom'

/**
 * Icon configuration for each validator type
 */
export interface ValidatorIconConfig {
  /** The lucide icon component */
  icon: LucideIcon
  /** Human-readable label for the validator type */
  label: string
  /** Description of what this validator type does */
  description: string
  /** ARIA label for accessibility */
  ariaLabel: string
}

/**
 * Icon map defining icons for each validator type
 * Feature #74 Steps 1-6
 */
export const VALIDATOR_ICON_MAP: Record<ValidatorType | 'unknown', ValidatorIconConfig> = {
  /**
   * Step 2: test_pass - Terminal icon
   * Validator that runs shell commands and checks exit codes
   */
  test_pass: {
    icon: Terminal,
    label: 'Test Pass',
    description: 'Runs a command and checks exit code',
    ariaLabel: 'Test pass validator (terminal)',
  },

  /**
   * Step 3: file_exists - File icon
   * Validator that checks if files or directories exist
   */
  file_exists: {
    icon: FileText,
    label: 'File Exists',
    description: 'Checks if a file or directory exists',
    ariaLabel: 'File exists validator (file)',
  },

  /**
   * Step 4: lint_clean - Code icon
   * Validator that runs linter and checks for errors
   */
  lint_clean: {
    icon: Code,
    label: 'Lint Clean',
    description: 'Runs linter and checks for errors',
    ariaLabel: 'Lint clean validator (code)',
  },

  /**
   * Step 5: forbidden_patterns - Shield icon
   * Validator that checks for forbidden regex patterns
   */
  forbidden_patterns: {
    icon: Shield,
    label: 'Forbidden Patterns',
    description: 'Checks output for forbidden patterns',
    ariaLabel: 'Forbidden patterns validator (shield)',
  },

  /**
   * Step 6: custom - Gear icon
   * Custom validators with user-defined logic
   */
  custom: {
    icon: Settings,
    label: 'Custom',
    description: 'Custom validator with user-defined logic',
    ariaLabel: 'Custom validator (gear)',
  },

  /**
   * Fallback for unknown validator types
   */
  unknown: {
    icon: HelpCircle,
    label: 'Unknown',
    description: 'Unknown validator type',
    ariaLabel: 'Unknown validator type',
  },
}

/**
 * Get the icon configuration for a validator type
 *
 * @param validatorType - The validator type string
 * @returns Icon configuration for the validator type
 */
export function getValidatorIconConfig(validatorType: string | undefined): ValidatorIconConfig {
  if (!validatorType) {
    return VALIDATOR_ICON_MAP.unknown
  }

  // Check if it's a known validator type
  const normalizedType = validatorType.toLowerCase().trim() as ValidatorType

  if (normalizedType in VALIDATOR_ICON_MAP) {
    return VALIDATOR_ICON_MAP[normalizedType]
  }

  return VALIDATOR_ICON_MAP.unknown
}

/**
 * Get the icon component for a validator type
 *
 * @param validatorType - The validator type string
 * @returns The Lucide icon component
 */
export function getValidatorIcon(validatorType: string | undefined): LucideIcon {
  return getValidatorIconConfig(validatorType).icon
}

/**
 * Get the human-readable label for a validator type
 *
 * @param validatorType - The validator type string
 * @returns Human-readable label
 */
export function getValidatorLabel(validatorType: string | undefined): string {
  return getValidatorIconConfig(validatorType).label
}

/**
 * Check if a validator type is known
 *
 * @param validatorType - The validator type string
 * @returns True if the validator type is known
 */
export function isKnownValidatorType(validatorType: string | undefined): boolean {
  if (!validatorType) return false
  const normalizedType = validatorType.toLowerCase().trim()
  return normalizedType in VALIDATOR_ICON_MAP && normalizedType !== 'unknown'
}

/**
 * Get all known validator types
 *
 * @returns Array of known validator type strings
 */
export function getKnownValidatorTypes(): ValidatorType[] {
  return ['test_pass', 'file_exists', 'lint_clean', 'forbidden_patterns', 'custom']
}
