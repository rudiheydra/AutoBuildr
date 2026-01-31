/**
 * useHandledMutation — wrapper around React Query's useMutation that enforces
 * consistent error handling via toast notifications.
 *
 * Every mutation in the app should surface backend failures to the user.
 * This helper automatically injects a default `onError` handler that shows
 * a toast with the error message, so developers cannot accidentally forget
 * error handling.
 *
 * Usage:
 *   import { useHandledMutation } from './useHandledMutation'
 *
 *   // Basic — uses default "Operation failed" title
 *   const mutation = useHandledMutation({
 *     mutationFn: (id: number) => api.deleteItem(id),
 *   })
 *
 *   // With custom error title
 *   const mutation = useHandledMutation({
 *     mutationFn: (id: number) => api.deleteItem(id),
 *     errorTitle: 'Failed to delete item',
 *   })
 *
 *   // Override onError entirely (opt-out of default toast)
 *   const mutation = useHandledMutation({
 *     mutationFn: (id: number) => api.deleteItem(id),
 *     onError: (error) => { customErrorHandler(error) },
 *   })
 *
 *   // Extend default toast with additional logic
 *   const mutation = useHandledMutation({
 *     mutationFn: (id: number) => api.deleteItem(id),
 *     errorTitle: 'Delete failed',
 *     onError: (error, variables, context) => {
 *       // This replaces the default toast — call toast.error yourself if needed
 *       toast.error('Custom message', error.message)
 *       rollbackOptimisticUpdate(context)
 *     },
 *   })
 */

import { useMutation, type UseMutationOptions, type UseMutationResult } from '@tanstack/react-query'
import { toast } from './useToast'

// ============================================================================
// Types
// ============================================================================

/**
 * Options accepted by useHandledMutation.
 *
 * Extends standard UseMutationOptions with an optional `errorTitle` field.
 * When `onError` is NOT provided by the caller, a default handler is injected
 * that calls `toast.error(errorTitle, error.message)`.
 *
 * When `onError` IS provided, it completely replaces the default toast handler,
 * giving callers full control over error presentation.
 */
export type UseHandledMutationOptions<
  TData = unknown,
  TError = Error,
  TVariables = void,
  TContext = unknown,
> = UseMutationOptions<TData, TError, TVariables, TContext> & {
  /**
   * Title shown in the error toast when the default onError handler fires.
   * Defaults to "Operation failed".
   */
  errorTitle?: string
}

// ============================================================================
// Hook
// ============================================================================

/**
 * A thin wrapper around `useMutation` that guarantees every mutation has an
 * `onError` handler. If the caller does not provide one, a default handler
 * is injected that shows a toast notification with the error message.
 *
 * @returns The same `UseMutationResult` that `useMutation` returns — fully
 *          compatible as a drop-in replacement.
 */
export function useHandledMutation<
  TData = unknown,
  TError = Error,
  TVariables = void,
  TContext = unknown,
>(
  options: UseHandledMutationOptions<TData, TError, TVariables, TContext>,
): UseMutationResult<TData, TError, TVariables, TContext> {
  const { errorTitle = 'Operation failed', onError, ...rest } = options

  // If caller supplied their own onError, respect it (opt-out).
  // Otherwise, inject the default toast handler.
  const effectiveOnError: typeof onError = onError
    ? onError
    : (error, _variables, _context) => {
        const message =
          error instanceof Error ? error.message : String(error)
        toast.error(errorTitle, message)
      }

  return useMutation<TData, TError, TVariables, TContext>({
    ...rest,
    onError: effectiveOnError,
  })
}
