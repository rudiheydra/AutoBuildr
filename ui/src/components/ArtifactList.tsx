/**
 * ArtifactList Component
 * ======================
 *
 * Displays a list of Artifacts for an AgentRun.
 * Used in the Run Inspector panel to show generated artifacts.
 *
 * Features:
 * - Filter dropdown by artifact_type
 * - Show artifact metadata: type, path, size
 * - Preview button for inline content
 * - Download button linking to /api/artifacts/:id/content
 * - Handles empty state gracefully
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import {
  FileCode,
  TestTube2,
  ScrollText,
  Activity,
  Camera,
  Filter,
  ChevronDown,
  Loader2,
  RefreshCw,
  AlertCircle,
  Eye,
  Download,
  X,
  File,
  HardDrive,
} from 'lucide-react'
import type { Artifact, ArtifactType } from '../lib/types'
import { getRunArtifacts, getArtifactContentUrl } from '../lib/api'

// =============================================================================
// Props Interface
// =============================================================================

interface ArtifactListProps {
  /** The AgentRun ID to fetch artifacts for */
  runId: string
  /** Optional callback when an artifact is clicked */
  onArtifactClick?: (artifact: Artifact) => void
  /** Optional className for container styling */
  className?: string
}

// =============================================================================
// Artifact Type Configuration
// =============================================================================

interface ArtifactTypeConfig {
  icon: typeof FileCode
  label: string
  color: string
  bgColor: string
}

const ARTIFACT_TYPE_CONFIG: Record<ArtifactType, ArtifactTypeConfig> = {
  file_change: {
    icon: FileCode,
    label: 'File Change',
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-100 dark:bg-blue-900/30',
  },
  test_result: {
    icon: TestTube2,
    label: 'Test Result',
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
  },
  log: {
    icon: ScrollText,
    label: 'Log',
    color: 'text-gray-600 dark:text-gray-400',
    bgColor: 'bg-gray-100 dark:bg-gray-900/30',
  },
  metric: {
    icon: Activity,
    label: 'Metric',
    color: 'text-purple-600 dark:text-purple-400',
    bgColor: 'bg-purple-100 dark:bg-purple-900/30',
  },
  snapshot: {
    icon: Camera,
    label: 'Snapshot',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-100 dark:bg-amber-900/30',
  },
}

// All valid artifact types for the filter dropdown
const ALL_ARTIFACT_TYPES: ArtifactType[] = [
  'file_change',
  'test_result',
  'log',
  'metric',
  'snapshot',
]

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Format bytes to human-readable size
 */
function formatSize(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return 'Unknown size'
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

/**
 * Format path for display (truncate long paths)
 */
function formatPath(path: string | null, maxLength: number = 40): string {
  if (!path) return 'No path'
  if (path.length <= maxLength) return path
  // Keep the filename and truncate the directory part
  const parts = path.split('/')
  const filename = parts[parts.length - 1]
  if (filename.length >= maxLength - 3) {
    return '...' + filename.slice(-(maxLength - 3))
  }
  return '...' + path.slice(-(maxLength - 3))
}

/**
 * Format timestamp for display
 */
function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// =============================================================================
// Preview Modal Component
// =============================================================================

interface PreviewModalProps {
  artifact: Artifact
  content: string | null
  isLoading: boolean
  error: string | null
  onClose: () => void
}

function PreviewModal({ artifact, content, isLoading, error, onClose }: PreviewModalProps) {
  const config = ARTIFACT_TYPE_CONFIG[artifact.artifact_type]
  const Icon = config.icon

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="preview-modal-title"
    >
      <div
        className="neo-card max-w-3xl w-full mx-4 max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-neo-border">
          <div className="flex items-center gap-2">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center ${config.bgColor}`}
            >
              <Icon size={16} className={config.color} aria-hidden="true" />
            </div>
            <div>
              <h3 id="preview-modal-title" className="font-display font-bold">{config.label} Preview</h3>
              <p className="text-xs text-neo-text-muted truncate max-w-md">
                {artifact.path || 'No path'}
              </p>
            </div>
          </div>
          <button
            className="neo-btn neo-btn-sm neo-btn-icon"
            onClick={onClose}
            title="Close"
            aria-label="Close preview modal"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-8">
              <Loader2 className="w-8 h-8 animate-spin text-neo-progress mb-2" />
              <p className="text-sm text-neo-text-secondary">Loading content...</p>
            </div>
          )}
          {error && (
            <div className="flex flex-col items-center justify-center py-8">
              <AlertCircle className="w-8 h-8 text-neo-danger mb-2" />
              <p className="text-sm text-neo-text-secondary">{error}</p>
            </div>
          )}
          {!isLoading && !error && content && (
            <pre
              className="
                text-xs font-mono p-4 rounded
                bg-neo-neutral-100 dark:bg-neo-neutral-800
                overflow-x-auto whitespace-pre-wrap break-words
              "
            >
              {content}
            </pre>
          )}
          {!isLoading && !error && !content && (
            <div className="flex flex-col items-center justify-center py-8">
              <File className="w-8 h-8 text-neo-text-muted mb-2" />
              <p className="text-sm text-neo-text-secondary">No content available</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 p-4 border-t border-neo-border">
          <a
            href={getArtifactContentUrl(artifact.id)}
            download
            className="neo-btn neo-btn-sm neo-btn-primary"
            aria-label={`Download ${config.label}`}
          >
            <Download size={14} aria-hidden="true" />
            Download
          </a>
          <button className="neo-btn neo-btn-sm" onClick={onClose} aria-label="Close preview modal">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// Single Artifact Card Component
// =============================================================================

interface ArtifactCardProps {
  artifact: Artifact
  onPreview: () => void
  onClick?: () => void
}

function ArtifactCard({ artifact, onPreview, onClick }: ArtifactCardProps) {
  const config = ARTIFACT_TYPE_CONFIG[artifact.artifact_type]
  const Icon = config.icon

  return (
    <div
      className="neo-card-flat p-3 hover:translate-x-1 transition-all duration-200"
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onClick()
              }
            }
          : undefined
      }
      aria-label={onClick ? `${config.label}: ${formatPath(artifact.path)}, ${formatSize(artifact.size_bytes)}` : undefined}
    >
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div
          className={`
            w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0
            ${config.bgColor}
          `}
        >
          <Icon size={20} className={config.color} aria-hidden="true" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Header row */}
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`neo-badge text-[10px] px-1.5 py-0.5 ${config.bgColor} ${config.color}`}
            >
              {config.label}
            </span>
            <span className="text-[10px] text-neo-text-muted">
              {formatTimestamp(artifact.created_at)}
            </span>
          </div>

          {/* Path */}
          <p
            className="text-sm text-neo-text-primary truncate font-mono"
            title={artifact.path || undefined}
          >
            {formatPath(artifact.path)}
          </p>

          {/* Metadata row */}
          <div className="flex items-center gap-3 mt-1 text-xs text-neo-text-muted">
            <span className="flex items-center gap-1">
              <HardDrive size={12} aria-hidden="true" />
              {formatSize(artifact.size_bytes)}
            </span>
            {artifact.has_inline_content && (
              <span className="text-green-600 dark:text-green-400">Previewable</span>
            )}
            {artifact.content_hash && (
              <span className="font-mono truncate max-w-[100px]" title={artifact.content_hash}>
                {artifact.content_hash.slice(0, 12)}...
              </span>
            )}
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 flex-shrink-0">
          {artifact.has_inline_content && (
            <button
              className="neo-btn neo-btn-sm neo-btn-icon"
              onClick={(e) => {
                e.stopPropagation()
                onPreview()
              }}
              title="Preview"
              aria-label={`Preview ${config.label}: ${formatPath(artifact.path)}`}
            >
              <Eye size={14} aria-hidden="true" />
            </button>
          )}
          <a
            href={getArtifactContentUrl(artifact.id)}
            download
            className="neo-btn neo-btn-sm neo-btn-icon"
            onClick={(e) => e.stopPropagation()}
            title="Download"
            aria-label={`Download ${config.label}: ${formatPath(artifact.path)}`}
          >
            <Download size={14} aria-hidden="true" />
          </a>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// Filter Dropdown Component
// =============================================================================

interface FilterDropdownProps {
  selectedType: ArtifactType | null
  onChange: (type: ArtifactType | null) => void
}

function FilterDropdown({ selectedType, onChange }: FilterDropdownProps) {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const selectedConfig = selectedType ? ARTIFACT_TYPE_CONFIG[selectedType] : null

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        className={`
          neo-btn neo-btn-sm flex items-center gap-1.5
          ${selectedType ? 'neo-btn-primary' : ''}
        `}
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={`Filter artifacts. Currently showing: ${selectedConfig ? selectedConfig.label : 'All Types'}`}
      >
        <Filter size={14} aria-hidden="true" />
        {selectedConfig ? selectedConfig.label : 'All Types'}
        <ChevronDown size={14} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>

      {isOpen && (
        <div
          className="absolute top-full left-0 mt-1 z-50 neo-dropdown min-w-[160px]"
          role="listbox"
          aria-label="Filter artifacts by type"
        >
          {/* All types option */}
          <button
            className={`
              neo-dropdown-item flex items-center gap-2
              ${selectedType === null ? 'bg-neo-pending' : ''}
            `}
            onClick={() => {
              onChange(null)
              setIsOpen(false)
            }}
            role="option"
            aria-selected={selectedType === null}
          >
            All Types
          </button>

          {/* Divider */}
          <div className="border-t border-neo-border my-1" aria-hidden="true" />

          {/* Artifact type options */}
          {ALL_ARTIFACT_TYPES.map((type) => {
            const config = ARTIFACT_TYPE_CONFIG[type]
            const Icon = config.icon
            return (
              <button
                key={type}
                className={`
                  neo-dropdown-item flex items-center gap-2
                  ${selectedType === type ? 'bg-neo-pending' : ''}
                `}
                onClick={() => {
                  onChange(type)
                  setIsOpen(false)
                }}
                role="option"
                aria-selected={selectedType === type}
              >
                <Icon size={14} className={config.color} aria-hidden="true" />
                {config.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// Main ArtifactList Component
// =============================================================================

export function ArtifactList({
  runId,
  onArtifactClick,
  className = '',
}: ArtifactListProps) {
  // State
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterType, setFilterType] = useState<ArtifactType | null>(null)

  // Preview modal state
  const [previewArtifact, setPreviewArtifact] = useState<Artifact | null>(null)
  const [previewContent, setPreviewContent] = useState<string | null>(null)
  const [isPreviewLoading, setIsPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)

  // Fetch artifacts from API
  const fetchArtifacts = useCallback(async () => {
    try {
      setIsLoading(true)
      setError(null)

      const data = await getRunArtifacts(runId, filterType || undefined)
      setArtifacts(data.artifacts)
      setTotal(data.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch artifacts')
    } finally {
      setIsLoading(false)
    }
  }, [runId, filterType])

  // Initial fetch and refetch on filter change
  useEffect(() => {
    fetchArtifacts()
  }, [fetchArtifacts])

  // Handle filter change
  const handleFilterChange = (type: ArtifactType | null) => {
    setFilterType(type)
  }

  // Handle refresh
  const handleRefresh = () => {
    fetchArtifacts()
  }

  // Handle preview
  const handlePreview = async (artifact: Artifact) => {
    setPreviewArtifact(artifact)
    setPreviewContent(null)
    setPreviewError(null)
    setIsPreviewLoading(true)

    try {
      const response = await fetch(getArtifactContentUrl(artifact.id))
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const text = await response.text()
      setPreviewContent(text)
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : 'Failed to load preview')
    } finally {
      setIsPreviewLoading(false)
    }
  }

  // Close preview
  const handleClosePreview = () => {
    setPreviewArtifact(null)
    setPreviewContent(null)
    setPreviewError(null)
    setIsPreviewLoading(false)
  }

  // Loading state
  if (isLoading) {
    return (
      <div className={`flex flex-col items-center justify-center p-8 ${className}`}>
        <Loader2 className="w-8 h-8 animate-spin text-neo-progress mb-2" />
        <p className="text-sm text-neo-text-secondary">Loading artifacts...</p>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className={`flex flex-col items-center justify-center p-8 ${className}`}>
        <AlertCircle className="w-8 h-8 text-neo-danger mb-2" />
        <p className="text-sm text-neo-text-secondary mb-3">{error}</p>
        <button className="neo-btn neo-btn-sm" onClick={handleRefresh} aria-label="Retry loading artifacts">
          <RefreshCw size={14} aria-hidden="true" />
          Retry
        </button>
      </div>
    )
  }

  // Empty state
  if (artifacts.length === 0) {
    return (
      <div className={`flex flex-col ${className}`}>
        {/* Header with filter */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <h3 className="font-display text-sm font-bold">Artifacts</h3>
            <span className="text-xs text-neo-text-muted">(0 artifacts)</span>
          </div>
          <div className="flex items-center gap-2">
            <FilterDropdown selectedType={filterType} onChange={handleFilterChange} />
            <button
              className="neo-btn neo-btn-sm neo-btn-icon"
              onClick={handleRefresh}
              title="Refresh"
              aria-label="Refresh artifacts list"
            >
              <RefreshCw size={14} aria-hidden="true" />
            </button>
          </div>
        </div>

        <div className="neo-empty-state">
          <File className="w-8 h-8 text-neo-text-muted mb-2" />
          <p className="text-neo-text-secondary">
            {filterType
              ? `No ${ARTIFACT_TYPE_CONFIG[filterType].label.toLowerCase()} artifacts found`
              : 'No artifacts generated yet'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={`flex flex-col ${className}`}>
      {/* Header with filter and refresh */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h3 className="font-display text-sm font-bold">Artifacts</h3>
          <span className="text-xs text-neo-text-muted">
            ({artifacts.length} of {total})
          </span>
        </div>
        <div className="flex items-center gap-2">
          <FilterDropdown selectedType={filterType} onChange={handleFilterChange} />
          <button
            className="neo-btn neo-btn-sm neo-btn-icon"
            onClick={handleRefresh}
            title="Refresh"
            aria-label="Refresh artifacts list"
            disabled={isLoading}
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Artifact list */}
      <div className="flex-1 overflow-y-auto space-y-2">
        {artifacts.map((artifact) => (
          <ArtifactCard
            key={artifact.id}
            artifact={artifact}
            onPreview={() => handlePreview(artifact)}
            onClick={onArtifactClick ? () => onArtifactClick(artifact) : undefined}
          />
        ))}
      </div>

      {/* Preview modal */}
      {previewArtifact && (
        <PreviewModal
          artifact={previewArtifact}
          content={previewContent}
          isLoading={isPreviewLoading}
          error={previewError}
          onClose={handleClosePreview}
        />
      )}
    </div>
  )
}

// Export types for use in parent components
export type { ArtifactListProps, Artifact, ArtifactType }
