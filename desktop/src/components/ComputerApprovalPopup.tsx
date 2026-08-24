/** 电脑审批共享逻辑：分类 + FIFO 队列 hook + 浮动卡片（供独立浮窗使用）。

分类/文案/队列的纯逻辑在 ``../approval/computerApproval``；
本模块只做 React 封装。
*/

import { useCallback, useEffect, useMemo, useReducer } from 'react'

import { approveApproval, denyApproval, listApprovals } from '../api/approvals'
import type { ApprovalRequest } from '../api/types'
import { connectComputerApprovalStream } from '../approval/computerApprovalStream'
import {
  initialFloatingApprovalState,
  reduceFloatingApprovalState,
  type FloatingApprovalPhase,
} from '../approval/floatingApprovalState'
import { rpcClient } from '../rpc'
import {
  computerActionDescription,
  computerActionLabel,
  computerActionSummary,
} from '../approval/computerApproval'

export {
  isComputerApproval,
  isDesktopApproval,
  isSandboxApproval,
  isChatApproval,
  chatShouldShowApproval,
  floatingShouldShowApproval,
  computerActionLabel,
  computerActionDescription,
  computerActionSummary,
  formatKeyShortcut,
} from '../approval/computerApproval'

export interface ApprovalQueueState {
  queue: ApprovalRequest[]
  active: ApprovalRequest | null
  busy: boolean
  error: string | null
  phase: FloatingApprovalPhase
  resolve: (decision: 'approve' | 'deny') => Promise<void>
  dismiss: () => void
}

/** 订阅审批事件，维护电脑审批 FIFO 队列（仅 computer_*）。 */
export function useComputerApprovalQueue(): ApprovalQueueState {
  const [state, dispatch] = useReducer(
    reduceFloatingApprovalState,
    initialFloatingApprovalState,
  )

  // 浮窗是独立 Renderer，必须自行维护 RPC 连接；重连后重新同步 pending。
  useEffect(() => {
    let cancelled = false
    const disconnect = connectComputerApprovalStream(rpcClient, {
      syncPending: async () => {
        const approvals = await listApprovals('pending')
        if (cancelled) return
        dispatch({ type: 'sync_pending', approvals })
      },
      onRequired: (approval) =>
        dispatch({ type: 'approval_required', approval }),
      onResolved: (approval) =>
        dispatch({ type: 'approval_resolved', approval }),
      onAgentEvent: (event) => dispatch({ type: 'agent_event', event }),
      onRunStatus: (runId, status) =>
        dispatch({ type: 'run_status', runId, status }),
      onConnectionError: () => {
        // RpcClient 自动重连；恢复后再次同步，不弹出没有审批内容的错误空窗。
      },
    })
    return () => {
      cancelled = true
      disconnect()
    }
  }, [])

  const resolve = useCallback(
    async (decision: 'approve' | 'deny'): Promise<void> => {
      if (!state.current) return
      dispatch({ type: 'submit_started' })
      try {
        const approval =
          decision === 'approve'
            ? await approveApproval(state.current.id)
            : await denyApproval(state.current.id)
        // approval resolved 只进入 executing/denied；真正完成等待 tool_completed。
        dispatch({ type: 'approval_resolved', approval })
      } catch (err) {
        dispatch({
          type: 'submit_failed',
          error: err instanceof Error ? err.message : String(err),
        })
      }
    },
    [state.current],
  )

  const queue = useMemo(
    () => (state.current ? [state.current, ...state.queue] : state.queue),
    [state.current, state.queue],
  )
  const dismiss = useCallback(() => dispatch({ type: 'dismiss' }), [])

  return {
    queue,
    active: state.current,
    busy: state.phase === 'submitting',
    error: state.error,
    phase: state.phase,
    resolve,
    dismiss,
  }
}

export interface ApprovalFloatingCardProps {
  approval: ApprovalRequest
  queuedCount?: number
  busy?: boolean
  error?: string | null
  phase?: FloatingApprovalPhase
  onApprove: (id: string) => void
  onDeny: (id: string) => void
}

/** 把审批 arguments 序列化成可供 Show details 展示的 JSON。 */
function formatArgumentsJson(argumentsValue: Record<string, unknown>): string {
  try {
    return JSON.stringify(argumentsValue, null, 2)
  } catch {
    return String(argumentsValue)
  }
}

/**
 * 浮窗内 macOS permission-panel 风格的展示卡片。
 * 主区域只放用户能看懂的动作与参数摘要；技术细节收进 Show details。
 */
export function ApprovalFloatingCard({
  approval,
  queuedCount = 0,
  busy = false,
  error = null,
  phase = 'pending',
  onApprove,
  onDeny,
}: ApprovalFloatingCardProps): React.JSX.Element {
  const label = computerActionLabel(approval)
  const description = computerActionDescription(approval)
  const summary = computerActionSummary(approval)
  const argsText = formatArgumentsJson(approval.arguments)
  const techLine = [
    approval.tool_name,
    approval.run_id ? `run: ${approval.run_id.slice(0, 8)}` : null,
  ]
    .filter(Boolean)
    .join(' · ')
  const presentation = floatingApprovalPresentation(phase, label, error)
  const canDecide = phase === 'pending' || phase === 'rpc_error'
  const showProgress = !canDecide

  return (
    <div className="floating-approval" data-testid="approval-floating-card">
      <header className="floating-approval__bar">
        <span className="floating-approval__brand">
          <span className="floating-approval__dot" aria-hidden="true" />
          Vesta
        </span>
        {queuedCount > 1 ? (
          <span className="floating-approval__waiting">
            还有 {queuedCount - 1} 项等待确认
          </span>
        ) : null}
      </header>

      <div className="floating-approval__body">
        <div className="floating-approval__eyebrow">{presentation.eyebrow}</div>
        <h2 className="floating-approval__title">{presentation.title}</h2>
        <p className="floating-approval__desc">
          {phase === 'pending' || phase === 'rpc_error'
            ? description
            : presentation.description}
        </p>
        {showProgress ? (
          <div className={`floating-approval__status floating-approval__status--${presentation.tone}`}>
            <span className="floating-approval__status-dot" aria-hidden="true" />
            {presentation.status}
          </div>
        ) : null}
        {summary ? (
          <div className="floating-approval__summary">{summary}</div>
        ) : null}

        <details className="floating-approval__details">
          <summary>查看技术详情</summary>
          {techLine ? (
            <div className="floating-approval__tech">{techLine}</div>
          ) : null}
          <pre className="floating-approval__json">{argsText}</pre>
        </details>

        {error ? (
          <details className="floating-approval__error">
            <summary>查看错误详情</summary>
            <code>{error}</code>
          </details>
        ) : null}
      </div>

      {canDecide ? <footer className="floating-approval__actions">
        <button
          type="button"
          className="floating-approval__btn floating-approval__btn--deny"
          disabled={busy}
          onClick={() => onDeny(approval.id)}
          aria-label={`拒绝${label}`}
        >
          暂不允许
        </button>
        <button
          type="button"
          className="floating-approval__btn floating-approval__btn--allow"
          disabled={busy}
          onClick={() => onApprove(approval.id)}
          aria-label={`允许${label}`}
        >
          允许
        </button>
      </footer> : null}
    </div>
  )
}

interface FloatingApprovalPresentation {
  eyebrow: string
  title: string
  description: string
  status: string
  tone: 'working' | 'success' | 'danger' | 'neutral'
}

/** 浮窗状态的人类可读文案；“投递成功”不会冒充“界面效果已验证”。 */
export function floatingApprovalPresentation(
  phase: FloatingApprovalPhase,
  actionLabel: string,
  error: string | null,
): FloatingApprovalPresentation {
  switch (phase) {
    case 'submitting':
      return { eyebrow: '正在提交', title: actionLabel, description: '正在发送你的选择，请稍候。', status: '提交确认中', tone: 'working' }
    case 'executing':
      return { eyebrow: '已允许', title: actionLabel, description: 'Vesta 正在执行你刚刚允许的电脑操作。', status: '正在执行', tone: 'working' }
    case 'action_delivered':
      return { eyebrow: '操作已发送', title: actionLabel, description: '操作事件已经发送，Vesta 正在确认界面是否真的发生变化。', status: '正在检查结果', tone: 'working' }
    case 'action_failed':
      return { eyebrow: '操作未完成', title: actionLabel, description: friendlyFloatingError(error, '这次电脑操作没有完成。'), status: 'Vesta 正在判断是否可以恢复', tone: 'danger' }
    case 'continuing':
      return { eyebrow: '继续执行', title: 'Vesta 正在继续任务', description: '刚才允许的操作已经结束，Vesta 正在处理下一步。', status: '任务执行中', tone: 'working' }
    case 'run_completed':
      return { eyebrow: '任务完成', title: '本轮执行已完成', description: 'Vesta 已经完成这次任务。', status: '已完成', tone: 'success' }
    case 'run_failed':
      return { eyebrow: '执行已停止', title: '本轮未能完成', description: friendlyFloatingError(error, 'Vesta 无法继续本轮任务，你可以返回会话查看详情。'), status: '需要你的关注', tone: 'danger' }
    case 'denied':
      return { eyebrow: '已拒绝', title: actionLabel, description: '这项电脑操作没有执行。', status: '操作已取消', tone: 'neutral' }
    case 'rpc_error':
      return { eyebrow: '提交失败', title: actionLabel, description: '暂时无法提交你的选择，请检查 Host 连接后重试。', status: '', tone: 'danger' }
    case 'pending':
      return { eyebrow: '需要你的确认', title: actionLabel, description: '', status: '', tone: 'neutral' }
  }
}

function friendlyFloatingError(
  error: string | null,
  fallback: string,
): string {
  if (!error) return fallback
  const normalized = error.toLowerCase()
  if (normalized.includes('maximum step') || normalized.includes('max_steps')) {
    return '执行步骤已达到上限。你可以返回会话，让 Vesta 从现有结果继续。'
  }
  if (normalized.includes('stale_observation') || normalized.includes('fresh observation')) {
    return '电脑画面已经变化。为了避免误操作，本次动作已安全停止。'
  }
  if (normalized.includes('permission') || normalized.includes('denied')) {
    return '这项操作没有获得允许，因此没有执行。'
  }
  return fallback
}
