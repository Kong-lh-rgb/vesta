/** Persistent AgentTurn：同一组件承载实时执行与完成后的 Work Record。 */

import type { AgentEvent } from '../api/types'
import {
  buildTurnView,
  formatCacheHitRate,
  formatDuration,
  formatTokens,
} from '../agent/turnPresentation'
import { useEventsStore } from '../stores/events'
import { AssistantContent } from './AssistantContent'

const STATUS = {
  thinking: { label: '正在思考', tone: 'working' },
  working: { label: '正在思考', tone: 'working' },
  waiting_approval: { label: '正在思考', tone: 'working' },
  verifying: { label: '正在思考', tone: 'working' },
  completed: { label: '已完成', tone: 'completed' },
  failed: { label: '已停止', tone: 'failed' },
  interrupted: { label: '已中断', tone: 'failed' },
  cancelled: { label: '已取消', tone: 'cancelled' },
} as const

export default function LiveAgentTurn({
  runId,
  step,
  events,
  settling = false,
  streamText,
  onRecover,
  onInspect,
}: {
  runId: string | null
  step: number | null
  events: AgentEvent[]
  settling?: boolean
  streamText?: string
  onRecover?: () => void
  onInspect?: () => void
}): React.JSX.Element {
  const liveText = useEventsStore((state) =>
    runId && step !== null && step !== undefined
      ? (state.streamTextByRun[runId]?.[step] ?? '')
      : '',
  )
  const view = buildTurnView(events, { now: Date.now() })
  const status = STATUS[view.status]
  const terminal = ['completed', 'failed', 'interrupted', 'cancelled'].includes(
    view.status,
  )
  const text = streamText !== undefined ? streamText : liveText || view.finalText

  return (
    <section
      className={`agent-turn live-turn agent-turn--${view.status}${settling ? ' live-turn--settling' : ''}`}
      aria-live="polite"
      aria-label="Vesta Agent Turn"
      data-status={view.status}
    >
      <header className="agent-turn__header">
        <div className="message-assistant__author">
          <span
            className={`message-assistant__avatar${!terminal ? ' message-assistant__avatar--busy' : ''}`}
            aria-hidden="true"
          />
          Vesta
        </div>
        {view.status !== 'completed' ? (
          <span className={`agent-turn__status agent-turn__status--${status.tone}`}>
            {status.label}
          </span>
        ) : null}
      </header>

      {view.error ? (
        <div className="agent-turn__error">
          <strong>{view.error.title}</strong>
          <p>{view.error.message}</p>
          {view.error.technical ? (
            <details className="agent-turn__error-details">
              <summary>查看技术详情</summary>
              <code>{view.error.technical}</code>
            </details>
          ) : null}
          <div className="agent-turn__error-actions">
            {view.status === 'interrupted' && onRecover ? (
              <button className="btn btn-primary btn-sm" onClick={onRecover}>
                恢复执行
              </button>
            ) : null}
            {onInspect ? (
              <button className="btn btn-sm" onClick={onInspect}>查看详情</button>
            ) : null}
          </div>
        </div>
      ) : text ? (
        <div className="live-turn__response agent-turn__response">
          <AssistantContent content={text} streaming={!terminal} />
          {!terminal ? <span className="stream-cursor" aria-hidden="true" /> : null}
        </div>
      ) : !terminal ? (
        <div className="live-turn__waiting">
          正在思考
        </div>
      ) : null}

      {view.steps > 0 || view.toolCount > 0 || view.usage || view.durationMs !== null ? (
        <footer className="turn-usage agent-turn__footer">
          第 {view.steps} 步
          {' · '}{view.toolCount} 次操作
          {view.usage ? (
            <>
              {' · '}输入 {formatTokens(view.usage.inputTokens)}
              {' · '}输出 {formatTokens(view.usage.outputTokens)}
              {' · '}缓存 {formatCacheHitRate(view.usage.cacheHitRate)}
            </>
          ) : null}
          {view.durationMs !== null ? ` · ${formatDuration(view.durationMs)}` : ''}
          {view.targetApp ? ` · 目标 ${view.targetApp}` : ''}
        </footer>
      ) : null}
    </section>
  )
}
