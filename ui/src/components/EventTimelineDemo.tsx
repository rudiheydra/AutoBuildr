/**
 * EventTimelineDemo Component
 * ===========================
 *
 * Demo page for testing the EventTimeline component.
 * Access via URL: /demo/timeline?runId=<run-id>
 */

import { useState } from 'react'
import { EventTimeline } from './EventTimeline'
import type { AgentEvent } from '../lib/types'

export function EventTimelineDemo() {
  // Get runId from URL search params
  const params = new URLSearchParams(window.location.search)
  const initialRunId = params.get('runId') || ''

  const [runId, setRunId] = useState(initialRunId)
  const [inputRunId, setInputRunId] = useState(initialRunId)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setRunId(inputRunId)
    // Update URL
    const newUrl = new URL(window.location.href)
    newUrl.searchParams.set('runId', inputRunId)
    window.history.pushState({}, '', newUrl.toString())
  }

  const handleEventClick = (event: AgentEvent) => {
    console.log('Event clicked:', event)
  }

  return (
    <div className="min-h-screen bg-neo-bg p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="font-display text-3xl font-bold mb-6">Event Timeline Demo</h1>

        {/* Run ID input form */}
        <form onSubmit={handleSubmit} className="mb-8">
          <div className="flex gap-4 items-end">
            <div className="flex-1">
              <label
                htmlFor="runId"
                className="block text-sm font-bold text-neo-text-secondary mb-2"
              >
                AgentRun ID
              </label>
              <input
                id="runId"
                type="text"
                value={inputRunId}
                onChange={(e) => setInputRunId(e.target.value)}
                placeholder="Enter AgentRun UUID..."
                className="neo-input"
              />
            </div>
            <button type="submit" className="neo-btn neo-btn-primary">
              Load Timeline
            </button>
          </div>
        </form>

        {/* Timeline component */}
        {runId ? (
          <div className="neo-card p-6">
            <EventTimeline
              runId={runId}
              onEventClick={handleEventClick}
              autoScroll={true}
              pageSize={25}
            />
          </div>
        ) : (
          <div className="neo-empty-state">
            <p className="text-neo-text-secondary">
              Enter an AgentRun ID above to view its event timeline.
            </p>
            <p className="text-sm text-neo-text-muted mt-2">
              You can also pass the runId as a URL parameter: ?runId=your-uuid
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
