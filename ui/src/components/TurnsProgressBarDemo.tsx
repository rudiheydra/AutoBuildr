/**
 * TurnsProgressBarDemo Component
 * ===============================
 *
 * Demo page for testing the TurnsProgressBar component across all
 * variations and edge cases.
 */

import { useState, useEffect } from 'react'
import { TurnsProgressBar } from './TurnsProgressBar'
import type { AgentRunStatus } from '../lib/types'

const statuses: AgentRunStatus[] = ['pending', 'running', 'paused', 'completed', 'failed', 'timeout']

export function TurnsProgressBarDemo() {
  // Animated demo state
  const [animatedUsed, setAnimatedUsed] = useState(0)
  const maxTurns = 50

  // Auto-increment for animation demo
  useEffect(() => {
    const interval = setInterval(() => {
      setAnimatedUsed(prev => (prev >= maxTurns ? 0 : prev + 1))
    }, 500)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8">
      <h1 className="font-display text-3xl mb-8">TurnsProgressBar Demo</h1>

      {/* Section: All Status Colors */}
      <section className="neo-card p-6">
        <h2 className="font-display text-xl mb-4">Status Color Variations</h2>
        <p className="text-sm text-neo-text-secondary mb-4">
          Each status has a distinct color. Hover over bars to see tooltip.
        </p>
        <div className="space-y-4">
          {statuses.map(status => (
            <div key={status} className="flex items-center gap-4">
              <span className="w-24 text-sm font-mono">{status}</span>
              <div className="flex-1">
                <TurnsProgressBar
                  used={status === 'completed' ? 50 : status === 'failed' ? 35 : status === 'timeout' ? 50 : 25}
                  max={50}
                  status={status}
                  showLabel={false}
                />
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Section: Animation Demo */}
      <section className="neo-card p-6">
        <h2 className="font-display text-xl mb-4">Animated Width Transition</h2>
        <p className="text-sm text-neo-text-secondary mb-4">
          Watch the smooth animation as progress increments.
        </p>
        <TurnsProgressBar
          used={animatedUsed}
          max={maxTurns}
          status="running"
          label="Animated Progress"
        />
        <p className="text-sm text-neo-text-muted mt-2">
          Current: {animatedUsed} / {maxTurns}
        </p>
      </section>

      {/* Section: Size Variants */}
      <section className="neo-card p-6">
        <h2 className="font-display text-xl mb-4">Size Variants</h2>
        <div className="space-y-4">
          <div>
            <p className="text-sm text-neo-text-secondary mb-2">Small (sm)</p>
            <TurnsProgressBar used={30} max={50} status="running" size="sm" />
          </div>
          <div>
            <p className="text-sm text-neo-text-secondary mb-2">Medium (md) - Default</p>
            <TurnsProgressBar used={30} max={50} status="running" size="md" />
          </div>
          <div>
            <p className="text-sm text-neo-text-secondary mb-2">Large (lg)</p>
            <TurnsProgressBar used={30} max={50} status="running" size="lg" />
          </div>
        </div>
      </section>

      {/* Section: Edge Cases */}
      <section className="neo-card p-6">
        <h2 className="font-display text-xl mb-4">Edge Cases</h2>
        <div className="space-y-4">
          <div>
            <p className="text-sm text-neo-text-secondary mb-2">max=0 (shows 0%)</p>
            <TurnsProgressBar used={0} max={0} status="pending" label="Zero max" />
          </div>
          <div>
            <p className="text-sm text-neo-text-secondary mb-2">max=0 with used &gt; 0 (overflow warning)</p>
            <TurnsProgressBar used={5} max={0} status="pending" label="Overflow case" />
          </div>
          <div>
            <p className="text-sm text-neo-text-secondary mb-2">used &gt; max (capped at 100%)</p>
            <TurnsProgressBar used={75} max={50} status="timeout" label="Exceeded max" />
          </div>
          <div>
            <p className="text-sm text-neo-text-secondary mb-2">Empty (0/100)</p>
            <TurnsProgressBar used={0} max={100} status="pending" label="Not started" />
          </div>
          <div>
            <p className="text-sm text-neo-text-secondary mb-2">Full (100/100)</p>
            <TurnsProgressBar used={100} max={100} status="completed" label="Complete" />
          </div>
        </div>
      </section>

      {/* Section: Without Label */}
      <section className="neo-card p-6">
        <h2 className="font-display text-xl mb-4">Without Label</h2>
        <p className="text-sm text-neo-text-secondary mb-4">
          Use showLabel=false for a cleaner look when labels are provided elsewhere.
        </p>
        <TurnsProgressBar used={35} max={50} status="running" showLabel={false} />
      </section>

      {/* Section: Custom Label */}
      <section className="neo-card p-6">
        <h2 className="font-display text-xl mb-4">Custom Label</h2>
        <TurnsProgressBar used={15} max={30} status="paused" label="API Calls" />
      </section>

      {/* Section: Integration Example */}
      <section className="neo-card p-6">
        <h2 className="font-display text-xl mb-4">Integration Example (Agent Card)</h2>
        <p className="text-sm text-neo-text-secondary mb-4">
          Shows how it looks integrated into an agent card context.
        </p>
        <div className="neo-card-flat p-4 max-w-sm border-2 border-neo-border">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-2xl" role="img" aria-label="coding">&#128187;</span>
            <div>
              <h3 className="font-display font-bold text-sm">feature-implementation</h3>
              <p className="text-xs text-neo-text-secondary">coding_agent_001</p>
            </div>
          </div>
          <span className="neo-status-badge neo-status-running inline-flex mb-3">
            Running
          </span>
          <TurnsProgressBar
            used={animatedUsed}
            max={maxTurns}
            status="running"
            className="mt-2"
          />
        </div>
      </section>
    </div>
  )
}

export default TurnsProgressBarDemo
