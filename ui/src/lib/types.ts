/**
 * TypeScript types for the Autonomous Coding UI
 */

// Project types
export interface ProjectStats {
  passing: number
  in_progress: number
  total: number
  percentage: number
}

export interface ProjectSummary {
  name: string
  path: string
  has_spec: boolean
  stats: ProjectStats
}

export interface ProjectDetail extends ProjectSummary {
  prompts_dir: string
}

// Filesystem types
export interface DriveInfo {
  letter: string
  label: string
  available?: boolean
}

export interface DirectoryEntry {
  name: string
  path: string
  is_directory: boolean
  has_children: boolean
}

export interface DirectoryListResponse {
  current_path: string
  parent_path: string | null
  entries: DirectoryEntry[]
  drives: DriveInfo[] | null
}

export interface PathValidationResponse {
  valid: boolean
  exists: boolean
  is_directory: boolean
  can_write: boolean
  message: string
}

export interface ProjectPrompts {
  app_spec: string
  initializer_prompt: string
  coding_prompt: string
}

// Feature types
export interface Feature {
  id: number
  priority: number
  category: string
  name: string
  description: string
  steps: string[]
  passes: boolean
  in_progress: boolean
  dependencies?: number[]           // Optional for backwards compat
  blocked?: boolean                 // Computed by API
  blocking_dependencies?: number[]  // Computed by API
}

// Status type for graph nodes
export type FeatureStatus = 'pending' | 'in_progress' | 'done' | 'blocked'

// Graph visualization types
export interface GraphNode {
  id: number
  name: string
  category: string
  status: FeatureStatus
  priority: number
  dependencies: number[]
}

export interface GraphEdge {
  source: number
  target: number
}

export interface DependencyGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface FeatureListResponse {
  pending: Feature[]
  in_progress: Feature[]
  done: Feature[]
}

export interface FeatureCreate {
  category: string
  name: string
  description: string
  steps: string[]
  priority?: number
  dependencies?: number[]
}

export interface FeatureUpdate {
  category?: string
  name?: string
  description?: string
  steps?: string[]
  priority?: number
  dependencies?: number[]
}

// Agent types
export type AgentStatus = 'stopped' | 'running' | 'paused' | 'crashed' | 'loading'

// ============================================================================
// AgentRun Types (from AgentSpec execution system)
// ============================================================================

// AgentRun status - lifecycle states for an agent run
export type AgentRunStatus = 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'timeout'

// AgentRun verdict - final outcome after acceptance check
export type AgentRunVerdict = 'passed' | 'failed' | 'error' | 'partial'

// AgentSpec task types
export type AgentSpecTaskType = 'coding' | 'testing' | 'refactoring' | 'documentation' | 'audit' | 'custom'

// AgentSpec summary for UI display
export interface AgentSpecSummary {
  id: string
  name: string
  display_name: string
  icon: string | null
  task_type: AgentSpecTaskType
  max_turns: number
  source_feature_id: number | null
}

/**
 * Acceptance validator result from the API
 * Includes validator type for icon display (Feature #74)
 */
export interface AcceptanceValidatorResult {
  passed: boolean
  message: string
  type?: string           // Validator type (test_pass, file_exists, etc.) - Feature #74
  score?: number          // Optional score for weighted validators
  required?: boolean      // Whether this is a required validator
  details?: Record<string, unknown>  // Optional debug details
}

// AgentRun for UI display
export interface AgentRun {
  id: string
  agent_spec_id: string
  status: AgentRunStatus
  started_at: string | null
  completed_at: string | null
  turns_used: number
  tokens_in: number
  tokens_out: number
  final_verdict: AgentRunVerdict | null
  acceptance_results: Record<string, AcceptanceValidatorResult> | null
  error: string | null
  retry_count: number
}

// Combined AgentSpec + Run for DynamicAgentCard
export interface DynamicAgentData {
  spec: AgentSpecSummary
  run: AgentRun | null
}

export interface AgentStatusResponse {
  status: AgentStatus
  pid: number | null
  started_at: string | null
  yolo_mode: boolean
  model: string | null  // Model being used by running agent
  parallel_mode: boolean  // DEPRECATED: Always true now (unified orchestrator)
  max_concurrency: number | null
  testing_agent_ratio: number  // Regression testing agents (0-3)
}

export interface AgentActionResponse {
  success: boolean
  status: AgentStatus
  message: string
}

// Setup types
export interface SetupStatus {
  claude_cli: boolean
  credentials: boolean
  node: boolean
  npm: boolean
}

// Dev Server types
export type DevServerStatus = 'stopped' | 'running' | 'crashed'

export interface DevServerStatusResponse {
  status: DevServerStatus
  pid: number | null
  url: string | null
  command: string | null
  started_at: string | null
}

export interface DevServerConfig {
  detected_type: string | null
  detected_command: string | null
  custom_command: string | null
  effective_command: string | null
}

// Terminal types
export interface TerminalInfo {
  id: string
  name: string
  created_at: string
}

// Agent mascot names for multi-agent UI
export const AGENT_MASCOTS = [
  'Spark', 'Fizz', 'Octo', 'Hoot', 'Buzz',    // Original 5
  'Pixel', 'Byte', 'Nova', 'Chip', 'Bolt',    // Tech-inspired
  'Dash', 'Zap', 'Gizmo', 'Turbo', 'Blip',    // Energetic
  'Neon', 'Widget', 'Zippy', 'Quirk', 'Flux', // Playful
] as const
export type AgentMascot = typeof AGENT_MASCOTS[number]

// Agent state for Mission Control
export type AgentState = 'idle' | 'thinking' | 'working' | 'testing' | 'success' | 'error' | 'struggling'

// Thinking state for DynamicAgentCard - represents current activity state
export type ThinkingState = 'idle' | 'thinking' | 'coding' | 'testing' | 'validating'

// Agent type (coding vs testing)
export type AgentType = 'coding' | 'testing'

// Individual log entry for an agent
export interface AgentLogEntry {
  line: string
  timestamp: string
  type: 'output' | 'state_change' | 'error'
}

// Agent update from backend
export interface ActiveAgent {
  agentIndex: number  // -1 for synthetic completions
  agentName: AgentMascot | 'Unknown'
  agentType: AgentType  // "coding" or "testing"
  featureId: number
  featureName: string
  state: AgentState
  thought?: string
  timestamp: string
  logs?: AgentLogEntry[]  // Per-agent log history
}

// Orchestrator state for Mission Control
export type OrchestratorState =
  | 'idle'
  | 'initializing'
  | 'scheduling'
  | 'spawning'
  | 'monitoring'
  | 'complete'

// Orchestrator event for recent activity
export interface OrchestratorEvent {
  eventType: string
  message: string
  timestamp: string
  featureId?: number
  featureName?: string
}

// Orchestrator status for Mission Control
export interface OrchestratorStatus {
  state: OrchestratorState
  message: string
  codingAgents: number
  testingAgents: number
  maxConcurrency: number
  readyCount: number
  blockedCount: number
  timestamp: string
  recentEvents: OrchestratorEvent[]
}

// WebSocket message types
export type WSMessageType = 'progress' | 'feature_update' | 'log' | 'agent_status' | 'pong' | 'dev_log' | 'dev_server_status' | 'agent_update' | 'orchestrator_update' | 'agent_run_started' | 'agent_event_logged' | 'agent_acceptance_update' | 'agent_spec_created'

export interface WSProgressMessage {
  type: 'progress'
  passing: number
  in_progress: number
  total: number
  percentage: number
}

export interface WSFeatureUpdateMessage {
  type: 'feature_update'
  feature_id: number
  passes: boolean
}

export interface WSLogMessage {
  type: 'log'
  line: string
  timestamp: string
  featureId?: number
  agentIndex?: number
  agentName?: AgentMascot
}

export interface WSAgentUpdateMessage {
  type: 'agent_update'
  agentIndex: number  // -1 for synthetic completions (untracked agents)
  agentName: AgentMascot | 'Unknown'
  agentType: AgentType  // "coding" or "testing"
  featureId: number
  featureName: string
  state: AgentState
  thought?: string
  timestamp: string
  synthetic?: boolean  // True for synthetic completions from untracked agents
}

export interface WSAgentStatusMessage {
  type: 'agent_status'
  status: AgentStatus
}

export interface WSPongMessage {
  type: 'pong'
}

export interface WSDevLogMessage {
  type: 'dev_log'
  line: string
  timestamp: string
}

export interface WSDevServerStatusMessage {
  type: 'dev_server_status'
  status: DevServerStatus
  url: string | null
}

export interface WSOrchestratorUpdateMessage {
  type: 'orchestrator_update'
  eventType: string
  state: OrchestratorState
  message: string
  timestamp: string
  codingAgents?: number
  testingAgents?: number
  maxConcurrency?: number
  readyCount?: number
  blockedCount?: number
  featureId?: number
  featureName?: string
}

// ============================================================================
// AgentSpec WebSocket Message Types (Phase 3 Real-time Updates)
// ============================================================================

/**
 * WebSocket message for agent_spec_created event.
 * Broadcast when a new AgentSpec is registered via the API.
 * Feature #146: Handle agent_spec_created WebSocket event in frontend UI.
 */
export interface WSAgentSpecCreatedMessage {
  type: 'agent_spec_created'
  spec_id: string
  name: string
  display_name: string
  icon: string | null
  task_type: string
  timestamp: string
}

// ============================================================================
// AgentRun WebSocket Message Types (Phase 3 Real-time Updates)
// ============================================================================

/**
 * WebSocket message for agent_run_started event.
 * Broadcast when an AgentRun begins execution.
 */
export interface WSAgentRunStartedMessage {
  type: 'agent_run_started'
  run_id: string
  spec_id: string
  display_name: string
  icon: string | null
  started_at: string
  timestamp: string
}

/**
 * WebSocket message for agent_event_logged event.
 * Broadcast for significant events during execution (tool_call, turn_complete, acceptance_check).
 */
export interface WSAgentEventLoggedMessage {
  type: 'agent_event_logged'
  run_id: string
  event_type: AgentEventType
  sequence: number
  tool_name?: string
  timestamp: string
}

/**
 * Validator result in acceptance update message.
 * Kept for backward compatibility with legacy WS array format.
 */
export interface WSValidatorResult {
  index: number
  type: string
  passed: boolean
  message: string
  score?: number
  details?: Record<string, unknown>
}

/**
 * WebSocket message for agent_acceptance_update event.
 * Broadcast when acceptance validators are evaluated.
 *
 * Feature #160: Now includes `acceptance_results` in canonical
 * Record<string, AcceptanceValidatorResult> format, matching the REST API.
 * The `validator_results` array is kept for backward compatibility.
 */
export interface WSAgentAcceptanceUpdateMessage {
  type: 'agent_acceptance_update'
  run_id: string
  final_verdict: AgentRunVerdict | null
  /** Canonical format: Record<string, AcceptanceValidatorResult> (Feature #160) */
  acceptance_results: Record<string, AcceptanceValidatorResult>
  /** Legacy array format kept for backward compatibility */
  validator_results: WSValidatorResult[]
  gate_mode: 'all_pass' | 'any_pass' | 'weighted'
  /** Payload format version for extensibility (Feature #160) */
  format_version?: number
  timestamp: string
}

export type WSMessage =
  | WSProgressMessage
  | WSFeatureUpdateMessage
  | WSLogMessage
  | WSAgentStatusMessage
  | WSAgentUpdateMessage
  | WSPongMessage
  | WSDevLogMessage
  | WSDevServerStatusMessage
  | WSOrchestratorUpdateMessage
  | WSAgentSpecCreatedMessage
  | WSAgentRunStartedMessage
  | WSAgentEventLoggedMessage
  | WSAgentAcceptanceUpdateMessage

// ============================================================================
// Spec Chat Types
// ============================================================================

export interface SpecQuestionOption {
  label: string
  description: string
}

export interface SpecQuestion {
  question: string
  header: string
  options: SpecQuestionOption[]
  multiSelect: boolean
}

export interface SpecChatTextMessage {
  type: 'text'
  content: string
}

export interface SpecChatQuestionMessage {
  type: 'question'
  questions: SpecQuestion[]
  tool_id?: string
}

export interface SpecChatCompleteMessage {
  type: 'spec_complete'
  path: string
}

export interface SpecChatFileWrittenMessage {
  type: 'file_written'
  path: string
}

export interface SpecChatSessionCompleteMessage {
  type: 'complete'
}

export interface SpecChatErrorMessage {
  type: 'error'
  content: string
}

export interface SpecChatPongMessage {
  type: 'pong'
}

export interface SpecChatResponseDoneMessage {
  type: 'response_done'
}

export type SpecChatServerMessage =
  | SpecChatTextMessage
  | SpecChatQuestionMessage
  | SpecChatCompleteMessage
  | SpecChatFileWrittenMessage
  | SpecChatSessionCompleteMessage
  | SpecChatErrorMessage
  | SpecChatPongMessage
  | SpecChatResponseDoneMessage

// Image attachment for chat messages
export interface ImageAttachment {
  id: string
  filename: string
  mimeType: 'image/jpeg' | 'image/png'
  base64Data: string    // Raw base64 (without data: prefix)
  previewUrl: string    // data: URL for display
  size: number          // File size in bytes
}

// UI chat message for display
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  attachments?: ImageAttachment[]
  timestamp: Date
  questions?: SpecQuestion[]
  isStreaming?: boolean
}

// ============================================================================
// Assistant Chat Types
// ============================================================================

export interface AssistantConversation {
  id: number
  project_name: string
  title: string | null
  created_at: string | null
  updated_at: string | null
  message_count: number
}

export interface AssistantMessage {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string | null
}

export interface AssistantConversationDetail {
  id: number
  project_name: string
  title: string | null
  created_at: string | null
  updated_at: string | null
  messages: AssistantMessage[]
}

export interface AssistantChatTextMessage {
  type: 'text'
  content: string
}

export interface AssistantChatToolCallMessage {
  type: 'tool_call'
  tool: string
  input: Record<string, unknown>
}

export interface AssistantChatResponseDoneMessage {
  type: 'response_done'
}

export interface AssistantChatErrorMessage {
  type: 'error'
  content: string
}

export interface AssistantChatConversationCreatedMessage {
  type: 'conversation_created'
  conversation_id: number
}

export interface AssistantChatPongMessage {
  type: 'pong'
}

export type AssistantChatServerMessage =
  | AssistantChatTextMessage
  | AssistantChatToolCallMessage
  | AssistantChatResponseDoneMessage
  | AssistantChatErrorMessage
  | AssistantChatConversationCreatedMessage
  | AssistantChatPongMessage

// ============================================================================
// Expand Chat Types
// ============================================================================

export interface ExpandChatFeaturesCreatedMessage {
  type: 'features_created'
  count: number
  features: { id: number; name: string; category: string }[]
}

export interface ExpandChatCompleteMessage {
  type: 'expansion_complete'
  total_added: number
}

export type ExpandChatServerMessage =
  | SpecChatTextMessage        // Reuse text message type
  | ExpandChatFeaturesCreatedMessage
  | ExpandChatCompleteMessage
  | SpecChatErrorMessage       // Reuse error message type
  | SpecChatPongMessage        // Reuse pong message type
  | SpecChatResponseDoneMessage // Reuse response_done type

// Bulk feature creation
export interface FeatureBulkCreate {
  features: FeatureCreate[]
  starting_priority?: number
}

export interface FeatureBulkCreateResponse {
  created: number
  features: Feature[]
}

// ============================================================================
// Settings Types
// ============================================================================

export interface ModelInfo {
  id: string
  name: string
}

export interface ModelsResponse {
  models: ModelInfo[]
  default: string
}

export interface Settings {
  yolo_mode: boolean
  model: string
  glm_mode: boolean
  ollama_mode: boolean
  testing_agent_ratio: number  // Regression testing agents (0-3)
}

export interface SettingsUpdate {
  yolo_mode?: boolean
  model?: string
  testing_agent_ratio?: number
}

// ============================================================================
// Schedule Types
// ============================================================================

export interface Schedule {
  id: number
  project_name: string
  start_time: string      // "HH:MM" in UTC
  duration_minutes: number
  days_of_week: number    // Bitfield: Mon=1, Tue=2, Wed=4, Thu=8, Fri=16, Sat=32, Sun=64
  enabled: boolean
  yolo_mode: boolean
  model: string | null
  max_concurrency: number // 1-5 concurrent agents
  crash_count: number
  created_at: string
}

export interface ScheduleCreate {
  start_time: string      // "HH:MM" format (local time, will be stored as UTC)
  duration_minutes: number
  days_of_week: number
  enabled: boolean
  yolo_mode: boolean
  model: string | null
  max_concurrency: number // 1-5 concurrent agents
}

export interface ScheduleUpdate {
  start_time?: string
  duration_minutes?: number
  days_of_week?: number
  enabled?: boolean
  yolo_mode?: boolean
  model?: string | null
  max_concurrency?: number
}

export interface ScheduleListResponse {
  schedules: Schedule[]
}

export interface NextRunResponse {
  has_schedules: boolean
  next_start: string | null  // ISO datetime in UTC
  next_end: string | null    // ISO datetime in UTC (latest end if overlapping)
  is_currently_running: boolean
  active_schedule_count: number
}

// ============================================================================
// AgentEvent Types (for Event Timeline)
// ============================================================================

// Event types from the backend AgentEvent model
// Kept in sync with api/agentspec_models.py EVENT_TYPES
export type AgentEventType =
  | 'started'
  | 'tool_call'
  | 'tool_result'
  | 'turn_complete'
  | 'acceptance_check'
  | 'completed'
  | 'failed'
  | 'paused'
  | 'resumed'
  | 'policy_violation'         // Feature #44: Tool policy violation logging
  | 'timeout'                  // Feature #134: Kernel timeout event recording
  | 'sdk_session_started'      // SDK session executor began
  | 'sdk_session_completed'    // SDK session executor finished
  | 'agent_planned'            // Feature #176/221: Maestro agent planning event
  | 'octo_failure'             // Feature #180: Octo failure audit event with fallback
  | 'agent_materialized'       // Feature #195: Materializer records agent file creation
  | 'tests_written'            // Feature #206: Test-runner writes test code from TestContract
  | 'tests_executed'           // Feature #207: Test-runner executes tests and reports results
  | 'test_result_artifact_created'  // Feature #212: Test result stored as artifact
  | 'sandbox_tests_executed'   // Feature #214: Test-runner runs tests in sandbox environment
  | 'icon_generated'           // Feature #218: Icon generation triggered during agent materialization

// Single event in the timeline
export interface AgentEvent {
  id: number
  run_id: string
  event_type: AgentEventType
  timestamp: string
  sequence: number
  payload: Record<string, unknown> | null
  payload_truncated: number | null
  artifact_ref: string | null
  tool_name: string | null
}

// Response from GET /api/agent-runs/:id/events
export interface AgentEventListResponse {
  events: AgentEvent[]
  total: number
  run_id: string
  start_sequence: number | null
  end_sequence: number | null
  has_more: boolean
}

// ============================================================================
// Artifact Types (for Artifact List component)
// ============================================================================

// Artifact types from the backend model
export type ArtifactType = 'file_change' | 'test_result' | 'log' | 'metric' | 'snapshot'

// Single artifact in the list (without inline content for performance)
export interface Artifact {
  id: string
  run_id: string
  artifact_type: ArtifactType
  path: string | null
  content_ref: string | null
  content_hash: string | null
  size_bytes: number | null
  created_at: string
  metadata: Record<string, unknown> | null
  has_inline_content: boolean
}

// Response from GET /api/agent-runs/:id/artifacts
export interface ArtifactListResponse {
  artifacts: Artifact[]
  total: number
  run_id: string
}
