/**
 * LoadingStateDemo Component
 * ==========================
 *
 * A demonstration page for Feature #84: Loading State Indicators
 * Shows all loading state components in action.
 *
 * Includes:
 * - Skeleton loaders for DynamicAgentCard
 * - Loading spinners for action buttons
 * - Run Inspector loading states
 * - Event timeline pagination loading
 * - Optimistic update demonstration
 */

import { useState, useCallback } from 'react'
import { Play, Pause, Square, RefreshCw } from 'lucide-react'
import {
  SkeletonText,
  SkeletonCircle,
  SkeletonRect,
  DynamicAgentCardSkeleton,
  EventTimelineSkeleton,
  ArtifactListSkeleton,
  RunInspectorSkeleton,
  EventCardSkeleton,
  ArtifactCardSkeleton,
} from './Skeleton'
import { LoadingButton, ActionButton } from './LoadingButton'
import { DynamicAgentCard } from './DynamicAgentCard'
import { RunInspector } from './RunInspector'
import type { DynamicAgentData, AgentRunStatus } from '../lib/types'

// =============================================================================
// Mock Data
// =============================================================================

const mockSpecData: DynamicAgentData = {
  spec: {
    id: 'demo-spec-1',
    name: 'demo-coding-agent',
    display_name: 'Demo Coding Agent',
    icon: '💻',
    task_type: 'coding',
    max_turns: 50,
    source_feature_id: 84,
  },
  run: {
    id: 'demo-run-1',
    agent_spec_id: 'demo-spec-1',
    status: 'running',
    started_at: new Date().toISOString(),
    completed_at: null,
    turns_used: 12,
    tokens_in: 15000,
    tokens_out: 8000,
    final_verdict: null,
    acceptance_results: null,
    error: null,
    retry_count: 0,
  },
}

const mockCompletedData: DynamicAgentData = {
  spec: {
    id: 'demo-spec-2',
    name: 'demo-testing-agent',
    display_name: 'Demo Testing Agent',
    icon: '🧪',
    task_type: 'testing',
    max_turns: 30,
    source_feature_id: 85,
  },
  run: {
    id: 'demo-run-2',
    agent_spec_id: 'demo-spec-2',
    status: 'completed',
    started_at: new Date(Date.now() - 300000).toISOString(),
    completed_at: new Date().toISOString(),
    turns_used: 25,
    tokens_in: 20000,
    tokens_out: 12000,
    final_verdict: 'passed',
    acceptance_results: {
      'test_pass': { passed: true, message: 'All tests passed (15/15)' },
      'lint_clean': { passed: true, message: 'No linting errors found' },
    },
    error: null,
    retry_count: 0,
  },
}

// =============================================================================
// Section Components
// =============================================================================

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <h2 className="font-display text-lg font-bold mb-4 text-neo-accent">{title}</h2>
      <div className="space-y-4">{children}</div>
    </div>
  )
}

function SubSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h3 className="font-medium text-sm text-neo-text-secondary mb-2">{title}</h3>
      {children}
    </div>
  )
}

// =============================================================================
// Main Demo Component
// =============================================================================

export function LoadingStateDemo() {
  const [isLoading, setIsLoading] = useState(false)
  const [showInspector, setShowInspector] = useState(false)
  const [inspectorLoading, setInspectorLoading] = useState(false)
  const [cardStatus, setCardStatus] = useState<AgentRunStatus>('running')

  // Simulate loading toggle
  const toggleLoading = () => {
    setIsLoading(true)
    setTimeout(() => setIsLoading(false), 2000)
  }

  // Simulate async action
  const simulateAction = useCallback(async () => {
    await new Promise(resolve => setTimeout(resolve, 1500))
  }, [])

  // Simulate action that fails
  const simulateFailingAction = useCallback(async () => {
    await new Promise((_, reject) => setTimeout(() => reject(new Error('Network error')), 1000))
  }, [])

  // Open inspector with loading state
  const openInspector = () => {
    setShowInspector(true)
    setInspectorLoading(true)
    setTimeout(() => setInspectorLoading(false), 1500)
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="font-display text-2xl font-bold mb-2">Feature #84: Loading State Indicators</h1>
      <p className="text-neo-text-secondary mb-8">
        Demonstration of loading states, skeleton loaders, and optimistic updates.
      </p>

      {/* Skeleton Loaders Section */}
      <Section title="1. Skeleton Loaders">
        <SubSection title="Basic Skeletons">
          <div className="space-y-2 p-4 neo-card-flat">
            <SkeletonText width="100%" />
            <SkeletonText width="75%" />
            <SkeletonText width="50%" />
            <div className="flex gap-4 mt-4">
              <SkeletonCircle size={40} />
              <SkeletonCircle size={32} />
              <SkeletonCircle size={24} />
            </div>
            <SkeletonRect width="100%" height={80} className="mt-4" />
          </div>
        </SubSection>

        <SubSection title="DynamicAgentCard Skeleton">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <DynamicAgentCardSkeleton />
            <DynamicAgentCard data={mockSpecData} onClick={() => openInspector()} />
          </div>
        </SubSection>

        <SubSection title="Event Card & Artifact Card Skeletons">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-neo-text-muted mb-2">Event Card Skeleton:</p>
              <EventCardSkeleton />
              <EventCardSkeleton />
            </div>
            <div>
              <p className="text-xs text-neo-text-muted mb-2">Artifact Card Skeleton:</p>
              <ArtifactCardSkeleton />
              <ArtifactCardSkeleton className="mt-2" />
            </div>
          </div>
        </SubSection>

        <SubSection title="Event Timeline Skeleton">
          <div className="neo-card-flat p-4 max-h-64 overflow-hidden">
            <EventTimelineSkeleton eventCount={3} />
          </div>
        </SubSection>

        <SubSection title="Artifact List Skeleton">
          <div className="neo-card-flat p-4 max-h-64 overflow-hidden">
            <ArtifactListSkeleton artifactCount={2} />
          </div>
        </SubSection>
      </Section>

      {/* Loading Buttons Section */}
      <Section title="2. Loading Buttons with Spinners">
        <SubSection title="LoadingButton Variants">
          <div className="flex flex-wrap gap-4">
            <LoadingButton
              isLoading={isLoading}
              loadingText="Loading..."
              onClick={toggleLoading}
            >
              Click to Load
            </LoadingButton>
            <LoadingButton
              isLoading={isLoading}
              variant="primary"
              icon={<Play size={16} />}
              onClick={toggleLoading}
            >
              Primary
            </LoadingButton>
            <LoadingButton
              isLoading={isLoading}
              variant="success"
              icon={<Play size={16} />}
              onClick={toggleLoading}
            >
              Success
            </LoadingButton>
            <LoadingButton
              isLoading={isLoading}
              variant="warning"
              icon={<Pause size={16} />}
              onClick={toggleLoading}
            >
              Warning
            </LoadingButton>
            <LoadingButton
              isLoading={isLoading}
              variant="danger"
              icon={<Square size={16} />}
              onClick={toggleLoading}
            >
              Danger
            </LoadingButton>
          </div>
        </SubSection>

        <SubSection title="Icon Buttons">
          <div className="flex gap-4">
            <LoadingButton
              isLoading={isLoading}
              size="icon"
              icon={<RefreshCw size={16} />}
              onClick={toggleLoading}
              title="Refresh"
            />
            <LoadingButton
              isLoading={isLoading}
              size="icon"
              variant="primary"
              icon={<Play size={16} />}
              onClick={toggleLoading}
              title="Play"
            />
            <LoadingButton
              isLoading={isLoading}
              size="icon"
              variant="danger"
              icon={<Square size={16} />}
              onClick={toggleLoading}
              title="Stop"
            />
          </div>
        </SubSection>

        <SubSection title="ActionButton with Error Handling">
          <div className="flex gap-4">
            <ActionButton
              actionName="Successful Action"
              icon={<Play size={16} />}
              onClick={simulateAction}
              variant="success"
              title="This will succeed after 1.5s"
            />
            <ActionButton
              actionName="Failing Action"
              icon={<Square size={16} />}
              onClick={simulateFailingAction}
              variant="danger"
              title="This will fail with error"
            />
          </div>
          <p className="text-xs text-neo-text-muted mt-2">
            Click the danger button to see error feedback with auto-dismiss.
          </p>
        </SubSection>
      </Section>

      {/* Run Inspector Section */}
      <Section title="3. Run Inspector with Loading States">
        <SubSection title="Inspector Demo">
          <div className="flex gap-4">
            <LoadingButton
              variant="primary"
              onClick={openInspector}
              icon={<Play size={16} />}
            >
              Open Inspector (with loading)
            </LoadingButton>
            <LoadingButton
              onClick={() => setShowInspector(true)}
            >
              Open Inspector (instant)
            </LoadingButton>
          </div>
        </SubSection>

        <SubSection title="Run Inspector Skeleton (inline preview)">
          <div className="neo-card max-w-md h-96 overflow-hidden">
            <RunInspectorSkeleton />
          </div>
        </SubSection>
      </Section>

      {/* Status Transitions */}
      <Section title="4. Agent Card Status Transitions">
        <SubSection title="Card with Different Statuses">
          <div className="flex flex-wrap gap-2 mb-4">
            {(['pending', 'running', 'paused', 'completed', 'failed', 'timeout'] as AgentRunStatus[]).map(status => (
              <LoadingButton
                key={status}
                size="sm"
                variant={cardStatus === status ? 'primary' : 'default'}
                onClick={() => setCardStatus(status)}
              >
                {status}
              </LoadingButton>
            ))}
          </div>
          <div className="max-w-xs">
            <DynamicAgentCard
              data={{
                ...mockSpecData,
                run: mockSpecData.run ? {
                  ...mockSpecData.run,
                  status: cardStatus,
                  final_verdict: cardStatus === 'completed' ? 'passed' : cardStatus === 'failed' ? 'failed' : null,
                  error: cardStatus === 'failed' ? 'Test assertion failed: Expected 42 but got 41' : null,
                } : null,
              }}
              onClick={() => setShowInspector(true)}
            />
          </div>
        </SubSection>
      </Section>

      {/* Run Inspector Modal */}
      <RunInspector
        data={mockCompletedData}
        isOpen={showInspector}
        onClose={() => setShowInspector(false)}
        isLoading={inspectorLoading}
        onPause={async () => { await simulateAction() }}
        onResume={async () => { await simulateAction() }}
        onCancel={async () => { await simulateAction() }}
      />
    </div>
  )
}

export default LoadingStateDemo
