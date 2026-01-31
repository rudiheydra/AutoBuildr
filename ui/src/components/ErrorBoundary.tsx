import { Component, type ReactNode, type ErrorInfo } from 'react'
import { AlertTriangle, RefreshCw, Copy, Check } from 'lucide-react'

interface ErrorBoundaryProps {
  children: ReactNode
  /** Optional fallback UI to render instead of the default error screen */
  fallback?: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
  copied: boolean
}

/**
 * Top-level React ErrorBoundary that wraps the main content area.
 *
 * Catches runtime errors in any child component and displays a
 * user-friendly fallback UI instead of crashing the entire application.
 * The app shell (header, sidebar, navigation) remains outside this
 * boundary and is always usable.
 *
 * Uses React class component APIs:
 * - getDerivedStateFromError: updates state to render fallback UI
 * - componentDidCatch: logs error details for debugging
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      copied: false,
    }
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    // Update state so the next render shows the fallback UI
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Log the error for debugging (visible in browser console)
    // Log with full stack trace as required by Feature #158
    console.error('[ErrorBoundary] Caught error in child component tree:', error)
    if (error.stack) {
      console.error('[ErrorBoundary] Full stack trace:', error.stack)
    }
    console.error('[ErrorBoundary] Component stack:', errorInfo.componentStack)

    this.setState({ errorInfo })
  }

  handleReset = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      copied: false,
    })
  }

  handleReload = (): void => {
    window.location.reload()
  }

  handleCopyError = async (): Promise<void> => {
    const { error, errorInfo } = this.state
    if (!error) return

    const errorDetails = [
      `${error.name}: ${error.message}`,
      '',
      'Stack trace:',
      error.stack || '(no stack trace available)',
    ]

    if (errorInfo?.componentStack) {
      errorDetails.push('', 'Component stack:', errorInfo.componentStack)
    }

    try {
      await navigator.clipboard.writeText(errorDetails.join('\n'))
      this.setState({ copied: true })
      // Reset copied state after 2 seconds
      setTimeout(() => {
        this.setState({ copied: false })
      }, 2000)
    } catch {
      // Fallback for environments where clipboard API is not available
      console.warn('[ErrorBoundary] Could not copy to clipboard')
    }
  }

  render(): ReactNode {
    if (this.state.hasError) {
      // If a custom fallback was provided, use it
      if (this.props.fallback) {
        return this.props.fallback
      }

      // Default fallback UI matching the neobrutalism design system
      return (
        <div className="flex items-center justify-center min-h-[60vh] px-4">
          <div className="neo-card p-8 max-w-lg w-full text-center">
            <div className="flex justify-center mb-4">
              <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center border-3 border-neo-border">
                <AlertTriangle size={32} className="text-red-600 dark:text-red-400" />
              </div>
            </div>

            <h2 className="font-display text-2xl font-bold mb-2 text-neo-text">
              Something went wrong
            </h2>
            <p className="text-neo-text-secondary mb-6">
              An unexpected error occurred in this section. The rest of the application
              is still working — you can use the header and navigation above.
            </p>

            {/* Error details (collapsed by default) */}
            {this.state.error && (
              <details className="mb-6 text-left">
                <summary className="cursor-pointer text-sm font-bold text-neo-text-secondary hover:text-neo-text transition-colors">
                  Show error details
                </summary>
                <div className="mt-2 p-3 bg-neo-bg rounded border-2 border-neo-border text-xs font-mono overflow-auto max-h-48">
                  <p className="text-red-600 dark:text-red-400 font-bold mb-1">
                    {this.state.error.name}: {this.state.error.message}
                  </p>
                  {this.state.error.stack && (
                    <pre className="text-neo-text-secondary whitespace-pre-wrap break-words mb-2">
                      {this.state.error.stack}
                    </pre>
                  )}
                  {this.state.errorInfo?.componentStack && (
                    <>
                      <p className="text-red-600 dark:text-red-400 font-bold mb-1 mt-2">
                        Component stack:
                      </p>
                      <pre className="text-neo-text-secondary whitespace-pre-wrap break-words">
                        {this.state.errorInfo.componentStack}
                      </pre>
                    </>
                  )}
                </div>
              </details>
            )}

            <div className="flex gap-3 justify-center flex-wrap">
              <button
                onClick={this.handleReset}
                className="neo-btn text-sm py-2 px-4 flex items-center gap-2"
              >
                <RefreshCw size={16} />
                Try Again
              </button>
              <button
                onClick={this.handleReload}
                className="neo-btn text-sm py-2 px-4 bg-neo-progress text-white border-neo-border flex items-center gap-2"
              >
                <RefreshCw size={16} />
                Reload
              </button>
              {this.state.error && (
                <button
                  onClick={this.handleCopyError}
                  className="neo-btn text-sm py-2 px-4 flex items-center gap-2"
                >
                  {this.state.copied ? <Check size={16} className="text-green-600" /> : <Copy size={16} />}
                  {this.state.copied ? 'Copied!' : 'Copy error details'}
                </button>
              )}
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
