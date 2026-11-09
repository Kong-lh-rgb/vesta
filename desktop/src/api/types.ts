/** Vesta Host JSON-RPC types. Wire models are generated from Backend Pydantic models. */
import type {
  AgentEvent as WireAgentEvent,
  AgentResult as WireAgentResult,
  MemoryRecord,
  Message as WireMessage,
  ModelUsage as WireModelUsage,
  Run,
  RunUsageSummary as WireRunUsageSummary,
  ToolResult as WireToolResult,
} from './backendModels.generated'

export type {
  AgentEvent as SerializedAgentEvent,
  AgentEventType,
  AgentMode,
  AgentResult as SerializedAgentResult,
  AgentRunTrace,
  ApprovalRequest,
  ApprovalRequestStatus as ApprovalStatus,
  Automation,
  AutomationStatus,
  Conversation,
  MemoryRecord as LongTermMemory,
  MemoryStatus,
  MessageRole,
  Message as SerializedMessage,
  Run,
  RunStatus,
  RunUsageSummary as SerializedRunUsageSummary,
  Schedule,
  ScheduleKind as AutomationKind,
  Task,
  TaskStatus,
  TaskStep,
  ToolCall,
} from './backendModels.generated'

/** UI inputs and legacy fixtures may omit Pydantic fields with defaults. */
type WithDefaults<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>

export type Message = WithDefaults<WireMessage, 'name' | 'tool_call_id' | 'tool_calls' | 'reasoning'>
export type ModelUsage = WithDefaults<WireModelUsage,
  'cached_input_tokens' | 'uncached_input_tokens' | 'cache_read_input_tokens' |
  'cache_write_input_tokens' | 'model_calls'>
export type ToolResult = WithDefaults<WireToolResult,
  'evidence_id' | 'output_chars' | 'output_sha256' | 'output_truncated' | 'evidence_error'>
export type AgentResult = Omit<WithDefaults<WireAgentResult,
  'tool_rounds' | 'tool_calls' | 'summary_state'>, 'usage'> & { usage: ModelUsage }

type EventCore = Pick<WireAgentEvent,
  'event_id' | 'run_id' | 'conversation_id' | 'sequence' | 'type' |
  'event_time' | 'step' | 'provider' | 'model' | 'message' |
  'tool_call' | 'tool_result' | 'usage' | 'stop_reason' | 'approval_decision'>
type EventNested = 'message' | 'tool_result' | 'usage' | 'summary_usage' | 'result'
export type AgentEvent = Omit<EventCore, EventNested> &
  Partial<Omit<WireAgentEvent, keyof EventCore | EventNested>> & {
    message: Message | null
    tool_result: ToolResult | null
    usage: ModelUsage | null
    summary_usage?: ModelUsage | null
    result?: AgentResult | null
  }

type UsageGroups = 'main_agent' | 'context_summary' | 'memory_reflection' |
  'memory_maintenance' | 'provider_total'
export type RunUsageSummary = Omit<WireRunUsageSummary, UsageGroups> &
  Record<UsageGroups, ModelUsage>

/** memory.list is an RPC response assembled from Core and MemoryRecord models. */
export interface LongTermMemoryOverview {
  core: string
  active: MemoryRecord[]
  archived: MemoryRecord[]
  active_count: number
  max_active: number
}

/** conversation.send is an RPC response assembled from Run and AgentResult. */
export interface SendMessageResponse {
  conversation_id: string
  content: string | null
  run: Run
  result: WireAgentResult
  plan_task_id: string | null
}

export interface Health {
  status: string
  provider: string
  model: string
  version: string
}

export type WsMessage =
  | { type: 'agent_event'; data: WireAgentEvent }
  | { type: 'run_status'; data: { run_id: string; status: string } }
