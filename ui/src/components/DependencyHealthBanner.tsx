import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getDependencyHealth } from '../lib/api'
import { AlertTriangle, X } from 'lucide-react'

interface DependencyHealthBannerProps {
  projectName: string | null
}

const DISMISSED_KEY_PREFIX = 'dependency-health-dismissed-'

export function DependencyHealthBanner({ projectName }: DependencyHealthBannerProps) {
  const [isDismissed, setIsDismissed] = useState(false)

  // Fetch dependency health status
  const { data: healthData, isLoading, isError } = useQuery({
    queryKey: ['dependencyHealth', projectName],
    queryFn: () => getDependencyHealth(projectName!),
    enabled: !!projectName && !isDismissed,
    refetchInterval: 30000, // Refresh every 30 seconds
    retry: false, // Don't retry on error
  })

  // Check if banner was previously dismissed for this session
  useEffect(() => {
    if (projectName) {
      const key = `${DISMISSED_KEY_PREFIX}${projectName}`
      const dismissed = sessionStorage.getItem(key)
      setIsDismissed(dismissed === 'true')
    }
  }, [projectName])

  const handleDismiss = () => {
    if (projectName) {
      const key = `${DISMISSED_KEY_PREFIX}${projectName}`
      sessionStorage.setItem(key, 'true')
    }
    setIsDismissed(true)
  }

  // Don't show if no project, loading, error, dismissed, or no issues
  if (!projectName || isLoading || isError || isDismissed || !healthData?.has_issues) {
    return null
  }

  return (
    <div
      className="bg-amber-100 dark:bg-amber-900/30 border-2 border-amber-500 dark:border-amber-600 rounded-lg px-4 py-3 flex items-center justify-between gap-3 shadow-neo-sm"
      role="alert"
      aria-live="polite"
    >
      <div className="flex items-center gap-3">
        <AlertTriangle
          className="text-amber-600 dark:text-amber-400 flex-shrink-0"
          size={20}
        />
        <span className="text-amber-800 dark:text-amber-200 font-medium text-sm">
          Warning: {healthData.count} dependency issue{healthData.count !== 1 ? 's' : ''} detected - see logs
        </span>
      </div>
      <button
        onClick={handleDismiss}
        className="text-amber-600 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-200 transition-colors p-1 rounded hover:bg-amber-200 dark:hover:bg-amber-800/50"
        aria-label="Dismiss warning"
        title="Dismiss"
      >
        <X size={18} />
      </button>
    </div>
  )
}
