/**
 * ResponsiveGridDemo Component
 * ============================
 *
 * Demonstration page for Feature #82: Mobile Responsive Agent Card Grid
 *
 * Tests:
 * 1. Responsive grid breakpoints (1/2/3/4 columns)
 * 2. Touch-friendly tap targets (min 44px)
 * 3. Full-width inspector on mobile
 * 4. Various screen sizes
 */

import { useState } from 'react'
import { DynamicAgentCard } from './DynamicAgentCard'
import { RunInspector } from './RunInspector'
import { DynamicAgentCardSkeleton } from './Skeleton'
import { useResponsiveColumns } from '../hooks/useResponsiveColumns'
import { useAgentCardGridNavigation } from '../hooks/useAgentCardGridNavigation'
import type { DynamicAgentData } from '../lib/types'

// =============================================================================
// Mock Data - Various agent statuses for testing
// =============================================================================

const mockAgents: DynamicAgentData[] = [
  {
    spec: {
      id: 'spec-1',
      name: 'coding-agent-feature-82',
      display_name: 'Coding Agent',
      icon: '💻',
      task_type: 'coding',
      max_turns: 50,
      source_feature_id: 82,
    },
    run: {
      id: 'run-1',
      agent_spec_id: 'spec-1',
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
  },
  {
    spec: {
      id: 'spec-2',
      name: 'testing-agent-unit',
      display_name: 'Testing Agent',
      icon: '🧪',
      task_type: 'testing',
      max_turns: 30,
      source_feature_id: 83,
    },
    run: {
      id: 'run-2',
      agent_spec_id: 'spec-2',
      status: 'completed',
      started_at: new Date(Date.now() - 300000).toISOString(),
      completed_at: new Date().toISOString(),
      turns_used: 25,
      tokens_in: 20000,
      tokens_out: 12000,
      final_verdict: 'passed',
      acceptance_results: {
        'test_pass': { passed: true, message: 'All tests passed' },
      },
      error: null,
      retry_count: 0,
    },
  },
  {
    spec: {
      id: 'spec-3',
      name: 'refactoring-agent',
      display_name: 'Refactoring Agent',
      icon: '🔧',
      task_type: 'refactoring',
      max_turns: 40,
      source_feature_id: null,
    },
    run: {
      id: 'run-3',
      agent_spec_id: 'spec-3',
      status: 'paused',
      started_at: new Date(Date.now() - 600000).toISOString(),
      completed_at: null,
      turns_used: 18,
      tokens_in: 10000,
      tokens_out: 6000,
      final_verdict: null,
      acceptance_results: null,
      error: null,
      retry_count: 0,
    },
  },
  {
    spec: {
      id: 'spec-4',
      name: 'documentation-agent',
      display_name: 'Documentation Agent',
      icon: '📝',
      task_type: 'documentation',
      max_turns: 20,
      source_feature_id: 84,
    },
    run: {
      id: 'run-4',
      agent_spec_id: 'spec-4',
      status: 'failed',
      started_at: new Date(Date.now() - 900000).toISOString(),
      completed_at: new Date(Date.now() - 800000).toISOString(),
      turns_used: 15,
      tokens_in: 8000,
      tokens_out: 4000,
      final_verdict: 'failed',
      acceptance_results: {
        'file_exists': { passed: false, message: 'README.md not found' },
      },
      error: 'Documentation generation failed: missing template file',
      retry_count: 1,
    },
  },
  {
    spec: {
      id: 'spec-5',
      name: 'audit-agent-security',
      display_name: 'Security Audit Agent',
      icon: '🔍',
      task_type: 'audit',
      max_turns: 60,
      source_feature_id: 85,
    },
    run: {
      id: 'run-5',
      agent_spec_id: 'spec-5',
      status: 'timeout',
      started_at: new Date(Date.now() - 1800000).toISOString(),
      completed_at: new Date(Date.now() - 100000).toISOString(),
      turns_used: 60,
      tokens_in: 50000,
      tokens_out: 30000,
      final_verdict: null,
      acceptance_results: null,
      error: 'Execution timed out after 1800 seconds',
      retry_count: 0,
    },
  },
  {
    spec: {
      id: 'spec-6',
      name: 'custom-agent-workflow',
      display_name: 'Custom Workflow Agent',
      icon: '⚙️',
      task_type: 'custom',
      max_turns: 100,
      source_feature_id: null,
    },
    run: {
      id: 'run-6',
      agent_spec_id: 'spec-6',
      status: 'pending',
      started_at: null,
      completed_at: null,
      turns_used: 0,
      tokens_in: 0,
      tokens_out: 0,
      final_verdict: null,
      acceptance_results: null,
      error: null,
      retry_count: 0,
    },
  },
]

// =============================================================================
// Main Demo Component
// =============================================================================

export function ResponsiveGridDemo() {
  const [selectedAgent, setSelectedAgent] = useState<DynamicAgentData | null>(null)
  const [showInspector, setShowInspector] = useState(false)

  // Responsive columns hook
  const { columns, deviceType, isMobile, isTablet, isTouchDevice, windowWidth } = useResponsiveColumns()

  // Grid navigation with responsive columns
  const { containerRef, getCardProps } = useAgentCardGridNavigation(
    mockAgents.length,
    {
      columns,
      onSelect: (index) => {
        setSelectedAgent(mockAgents[index])
        setShowInspector(true)
      },
    }
  )

  const handleCardClick = (agent: DynamicAgentData) => {
    setSelectedAgent(agent)
    setShowInspector(true)
  }

  const handleCloseInspector = () => {
    setShowInspector(false)
    setSelectedAgent(null)
  }

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto" data-testid="responsive-grid-demo">
      {/* Header */}
      <div className="mb-6">
        <h1 className="font-display text-2xl font-bold mb-2">
          Feature #82: Mobile Responsive Agent Card Grid
        </h1>
        <p className="text-neo-text-secondary mb-4">
          Resize the browser window to see responsive breakpoints in action.
        </p>

        {/* Device Info Panel */}
        <div
          className="neo-card-flat p-4 mb-6"
          data-testid="device-info-panel"
        >
          <h2 className="font-bold text-sm mb-3">Current Device Info</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 text-sm">
            <div>
              <span className="text-neo-text-muted">Device:</span>
              <span className="ml-2 font-mono font-bold" data-testid="device-type">{deviceType}</span>
            </div>
            <div>
              <span className="text-neo-text-muted">Width:</span>
              <span className="ml-2 font-mono" data-testid="window-width">{windowWidth}px</span>
            </div>
            <div>
              <span className="text-neo-text-muted">Columns:</span>
              <span className="ml-2 font-mono font-bold" data-testid="column-count">{columns}</span>
            </div>
            <div>
              <span className="text-neo-text-muted">Mobile:</span>
              <span className={`ml-2 font-bold ${isMobile ? 'text-neo-done' : 'text-neo-text-muted'}`}>
                {isMobile ? 'Yes' : 'No'}
              </span>
            </div>
            <div>
              <span className="text-neo-text-muted">Tablet:</span>
              <span className={`ml-2 font-bold ${isTablet ? 'text-neo-done' : 'text-neo-text-muted'}`}>
                {isTablet ? 'Yes' : 'No'}
              </span>
            </div>
            <div>
              <span className="text-neo-text-muted">Touch:</span>
              <span className={`ml-2 font-bold ${isTouchDevice ? 'text-neo-done' : 'text-neo-text-muted'}`}>
                {isTouchDevice ? 'Yes' : 'No'}
              </span>
            </div>
          </div>
        </div>

        {/* Breakpoint Reference */}
        <div className="neo-card-flat p-4 mb-6">
          <h2 className="font-bold text-sm mb-3">Responsive Breakpoints</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div className={`p-2 rounded ${deviceType === 'mobile' ? 'bg-neo-progress text-white' : 'bg-neo-neutral-200'}`}>
              <strong>Mobile</strong>: &lt;640px (1 col)
            </div>
            <div className={`p-2 rounded ${deviceType === 'tablet' ? 'bg-neo-progress text-white' : 'bg-neo-neutral-200'}`}>
              <strong>Tablet</strong>: 640-1023px (2 col)
            </div>
            <div className={`p-2 rounded ${deviceType === 'desktop' ? 'bg-neo-progress text-white' : 'bg-neo-neutral-200'}`}>
              <strong>Desktop</strong>: 1024-1279px (3 col)
            </div>
            <div className={`p-2 rounded ${deviceType === 'large' ? 'bg-neo-progress text-white' : 'bg-neo-neutral-200'}`}>
              <strong>Large</strong>: &ge;1280px (4 col)
            </div>
          </div>
        </div>
      </div>

      {/* Agent Card Grid */}
      <div
        ref={containerRef as React.RefObject<HTMLDivElement>}
        className="neo-agent-card-grid"
        role="grid"
        aria-label="Agent cards grid"
        data-testid="agent-card-grid"
      >
        {mockAgents.map((agent, index) => {
          const cardProps = getCardProps(index)
          return (
            <DynamicAgentCard
              key={agent.spec.id}
              data={agent}
              onClick={() => handleCardClick(agent)}
              tabIndex={cardProps.tabIndex}
              aria-selected={cardProps['aria-selected']}
              data-card-index={cardProps['data-card-index']}
              onKeyDown={cardProps.onKeyDown}
              onFocus={cardProps.onFocus}
              cardRef={cardProps.ref}
            />
          )
        })}
      </div>

      {/* Touch Target Demo Section */}
      <div className="mt-8 neo-card-flat p-4">
        <h2 className="font-bold text-sm mb-3">Touch Target Verification</h2>
        <p className="text-xs text-neo-text-muted mb-4">
          All interactive elements should have a minimum 44px touch target on mobile.
          The cards above include <code>min-h-[120px]</code> and <code>touch-manipulation</code> classes.
        </p>
        <div className="flex flex-wrap gap-4">
          <button
            className="neo-btn neo-btn-sm min-h-[44px]"
            data-testid="touch-target-button"
          >
            44px Touch Target
          </button>
          <div
            className="neo-badge bg-neo-progress text-white min-h-[44px] flex items-center"
            data-testid="touch-target-badge"
          >
            44px Badge
          </div>
        </div>
      </div>

      {/* Loading Skeleton Grid Demo */}
      <div className="mt-8">
        <h2 className="font-bold text-sm mb-3">Skeleton Loading States (Responsive)</h2>
        <div className="neo-agent-card-grid" data-testid="skeleton-grid">
          <DynamicAgentCardSkeleton />
          <DynamicAgentCardSkeleton />
          <DynamicAgentCardSkeleton />
        </div>
      </div>

      {/* Run Inspector (full-width on mobile) */}
      <RunInspector
        data={selectedAgent}
        isOpen={showInspector}
        onClose={handleCloseInspector}
      />
    </div>
  )
}

export default ResponsiveGridDemo
