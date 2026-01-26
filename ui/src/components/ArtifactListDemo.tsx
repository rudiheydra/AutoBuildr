/**
 * ArtifactListDemo Component
 * ==========================
 *
 * Demo page for testing the ArtifactList component.
 * Access via URL: /demo/artifacts?runId=<run-id>
 */

import { useState } from 'react'
import { ArtifactList } from './ArtifactList'
import type { Artifact } from '../lib/types'

export function ArtifactListDemo() {
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

  const handleArtifactClick = (artifact: Artifact) => {
    console.log('Artifact clicked:', artifact)
  }

  return (
    <div className="min-h-screen bg-neo-bg p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="font-display text-3xl font-bold mb-6">Artifact List Demo</h1>

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
              Load Artifacts
            </button>
          </div>
        </form>

        {/* Artifact list component */}
        {runId ? (
          <div className="neo-card p-6">
            <ArtifactList
              runId={runId}
              onArtifactClick={handleArtifactClick}
            />
          </div>
        ) : (
          <div className="neo-empty-state">
            <p className="text-neo-text-secondary">
              Enter an AgentRun ID above to view its artifacts.
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
