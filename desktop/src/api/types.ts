/** 与 Vesta Host JSON-RPC 对应的 Desktop 类型。 */
import type { Run } from './backendModels.generated'
export type {
  ApprovalRequest,
  ApprovalRequestStatus as ApprovalStatus,
  Automation,
  AutomationStatus,
  Schedule,
  ScheduleKind as AutomationKind,
  AgentMode,
  Conversation,
  Run,
  RunStatus,
  Task,
  TaskStatus,
  TaskStep,
} from './backendModels.generated'

export type MessageRole = 'system' | 'user' | 'assistant' | 'tool'

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown> | string
}

export interface Message {
  role: MessageRole
  content: string | null
  name?: string | null
  tool_call_id?: string | null
  tool_calls?: ToolCall[]
  /** 模型思考/推理内容（DeepSeek/Qwen reasoning_content、Anthropic thinking）。 */
  reasoning?: string | null
}

export interface ModelUsage {
  input_tokens: number
  output_tokens: number
  total_tokens: number
  cached_input_tokens?: number | null
  uncached_input_tokens?: number | null
  cache_read_input_tokens?: number | null
  cache_write_input_tokens?: number | null
  model_calls?: number
}

export interface RunUsageSummary {
  main_agent: ModelUsage
  context_summary: ModelUsage
  memory_reflection: ModelUsage
  memory_maintenance: ModelUsage
  provider_total: ModelUsage
  tool_schema_tokens_estimated: number
  memory_reflection_status: string
  memory_reflection_skip_reason: string | null
  context_summary_status: string
  context_summary_provider: string | null
  context_summary_model: string | null
  context_summary_duration_ms: number
  main_agent_chargeable_tokens: number
  run_budget_status: string
  run_budget_reason: string | null
  run_budget_warning_tokens: number | null
  run_budget_finalization_tokens: number | null
  run_budget_hard_tokens: number | null
  run_budget_warning_model_calls: number | null
  run_budget_finalization_model_calls: number | null
  run_budget_hard_model_calls: number | null
}

export interface LongTermMemory {
  id: string
  title: string
  summary: string
  content: string
  created_at: string
  updated_at: string
  last_accessed_at: string
  access_count: number
  revision: number
  status: 'active' | 'archived'
  last_update_reason: string | null
  archive_reason: string | null
}

export interface LongTermMemoryOverview {
  core: string
  active: LongTermMemory[]
  archived: LongTermMemory[]
  active_count: number
  max_active: number
}

export interface AgentResult {
  run_id: string
  final_message: Message
  messages: Message[]
  steps: number
  stop_reason: string
  usage: ModelUsage
  error: { type: string; message: string } | null
  plan_task_id: string | null
}

export interface SendMessageResponse {
  conversation_id: string
  content: string | null
  run: Run
  result: AgentResult
  plan_task_id: string | null
}

export interface AgentRunTrace {
  run_id: string
  conversation_id: string | null
  status: string
  started_at: string
  completed_at: string | null
  provider: string | null
  model: string | null
  steps: number
  stop_reason: string | null
  input_tokens: number
  output_tokens: number
  total_tokens: number
  event_count: number
}

export interface AgentEvent {
  event_id: string
  run_id: string
  conversation_id: string | null
  sequence: number
  type: string
  event_time: string
  step: number | null
  provider: string | null
  model: string | null
  delta?: string | null
  /** 旧 Trace 兼容字段；新 Runtime 不再发送 Provider 原始推理。 */
  reasoning_delta?: string | null
  message: Message | null
  tool_call: ToolCall | null
  tool_result: {
    tool_call_id: string
    tool_name: string
    success: boolean
    output: string | null
    error: string | null
    duration_ms: number
  } | null
  usage: ModelUsage | null
  stop_reason: string | null
  approval_decision: string | null
  /** memory_reflection_* 事件携带的观察字段（未触发/跳过/失败原因）。 */
  reflection_triggered?: boolean | null
  reflection_skip_reason?: string | null
  reflection_error?: string | null
  /** agent_completed / agent_failed 携带的最终结果（含 usage / steps）。 */
  result?: AgentResult | null
  original_estimated_input_tokens?: number | null
  prepared_input_tokens?: number | null
  estimated_input_tokens?: number | null
  context_trimmed?: boolean | null
  context_window?: number | null
  input_budget?: number | null
  working_input_budget?: number | null
  trigger_tokens?: number | null
  target_tokens?: number | null
  usage_ratio?: number | null
  tool_result_budget_tokens?: number | null
  tool_result_tokens_before?: number | null
  tool_result_tokens_after?: number | null
  tool_schema_tokens?: number | null
  message_tokens_before?: number | null
  message_tokens_after?: number | null
  original_usage_ratio?: number | null
  prepared_usage_ratio?: number | null
  compaction_stage?: string | null
  compacted_tool_results?: number | null
  removed_tool_rounds?: number | null
  reached_target?: boolean | null
  summary_updated?: boolean | null
  summarized_conversation_blocks?: number | null
  summary_error?: string | null
  summary_usage?: ModelUsage | null
  summary_provider?: string | null
  summary_model?: string | null
  summary_duration_ms?: number | null
  cache_prefix_reused?: boolean | null
  cache_prefix_message_count?: number | null
  available_skill_count?: number | null
  skill_catalog_tokens?: number | null
  active_skill_names?: string[]
  active_skill_tokens?: number | null
  [key: string]: unknown
}

export interface Health {
  status: string
  provider: string
  model: string
  version: string
}

export type WsMessage =
  | { type: 'agent_event'; data: AgentEvent }
  | { type: 'run_status'; data: { run_id: string; status: string } }
