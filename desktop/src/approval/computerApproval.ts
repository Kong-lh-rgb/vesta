/** 审批路由与展示的纯逻辑（无 React、无副作用，便于单元测试）。

路由依据：
- 声明式 ``ui_scope``：desktop → 始终进入浮窗；sandbox → 始终进入 Chat。
- 一条审批从出现到解决只归属一个 surface，焦点变化不能迁移审批。
后端是权威来源；``ui_scope`` 缺失时（旧数据）回退 tool_name 前缀。
*/

import type { ApprovalRequest } from '../api/types'

/**
 * Desktop 审批：作用于用户真实桌面，始终由独立浮窗处理。
 * 优先用后端声明的 ui_scope；缺失时（旧数据）回退 computer_ 前缀。
 */
export function isDesktopApproval(approval: ApprovalRequest): boolean {
  if (approval.ui_scope) return approval.ui_scope === 'desktop'
  return approval.tool_name.startsWith('computer_')
}

/** 兼容旧名：Computer Approval == Desktop Approval。 */
export function isComputerApproval(approval: ApprovalRequest): boolean {
  return isDesktopApproval(approval)
}

/** Sandbox 审批：作用于 Vesta 沙盒 / 宿主，永远进 Chat。 */
export function isSandboxApproval(approval: ApprovalRequest): boolean {
  return !isDesktopApproval(approval)
}

/** Chat 内是否展示：普通（sandbox）审批 + 属于当前 active Run。 */
export function isChatApproval(
  approval: ApprovalRequest,
  activeRunId: string | null,
): boolean {
  return isSandboxApproval(approval) && approval.run_id === activeRunId
}

/** Chat 路由：只有当前 Run 的 sandbox 审批进入 Chat。 */
export function chatShouldShowApproval(
  approval: ApprovalRequest,
  activeRunId: string | null,
): boolean {
  return isSandboxApproval(approval) && approval.run_id === activeRunId
}

/** 浮窗路由：所有 desktop 审批始终进入浮窗。 */
export function floatingShouldShowApproval(approval: ApprovalRequest): boolean {
  return isDesktopApproval(approval)
}

// ---------------------------------------------------------------------------
// 面向普通用户的动作文案（不要直接把 tool_name 丢给用户）
// ---------------------------------------------------------------------------

const ACTION_LABELS: Record<string, string> = {
  computer_click: '点击界面元素',
  computer_type: '输入文本',
  computer_key: '按下按键或快捷键',
  computer_scroll: '滚动当前窗口',
  computer_open_app: '打开应用',
  computer_focus_window: '切换到目标窗口',
}

const ACTION_DESCRIPTIONS: Record<string, string> = {
  computer_click: 'Vesta 准备点击当前应用中的界面元素。',
  computer_type: 'Vesta 准备向当前应用输入下面的文本。',
  computer_key: 'Vesta 准备向当前应用发送按键或快捷键。',
  computer_scroll: 'Vesta 准备滚动当前应用窗口。',
  computer_open_app: 'Vesta 准备打开一个应用。',
  computer_focus_window: 'Vesta 准备切换到目标应用窗口。',
}

/** 主要动作名（如“输入文本”）；未知 computer_* 使用通用电脑操作文案。 */
export function computerActionLabel(approval: ApprovalRequest): string {
  return ACTION_LABELS[approval.tool_name] ?? '操作这台 Mac'
}

/** 面向用户的电脑操作描述。 */
export function computerActionDescription(approval: ApprovalRequest): string {
  return (
    ACTION_DESCRIPTIONS[approval.tool_name] ??
    'Vesta 准备操作这台 Mac。'
  )
}

// ---------------------------------------------------------------------------
// Arguments 摘要（主区域只放用户能看懂的内容，原始 JSON 进 Show details）
// ---------------------------------------------------------------------------

const MODIFIER_SYMBOLS: Record<string, string> = {
  command: '⌘',
  cmd: '⌘',
  shift: '⇧',
  option: '⌥',
  alt: '⌥',
  control: '⌃',
  ctrl: '⌃',
}

const NAMED_KEYS: Record<string, string> = {
  enter: 'Return',
  return: 'Return',
  tab: 'Tab',
  escape: 'Esc',
  space: 'Space',
  backspace: '⌫',
  delete: '⌫',
  up: '↑',
  down: '↓',
  left: '←',
  right: '→',
}

function formatKeyName(key: string): string {
  const named = NAMED_KEYS[key]
  if (named) return named
  if (key.length === 1) return key.toUpperCase()
  return key
}

/** 把 key + modifiers 格式化成人类可读快捷键，如 ``⌘ N``。 */
export function formatKeyShortcut(
  key: string,
  modifiers: readonly string[],
): string {
  const symbols = modifiers
    .map((modifier) => MODIFIER_SYMBOLS[modifier] ?? '')
    .filter(Boolean)
  return [...symbols, formatKeyName(key)].join(' ')
}

/** 面向用户的动作参数摘要；无可展示内容返回 null。 */
export function computerActionSummary(approval: ApprovalRequest): string | null {
  const args = approval.arguments ?? {}
  switch (approval.tool_name) {
    case 'computer_type': {
      const text = typeof args.text === 'string' ? args.text.trim() : ''
      return text ? `“${text}”` : null
    }
    case 'computer_key': {
      const key = typeof args.key === 'string' ? args.key : ''
      const modifiers = Array.isArray(args.modifiers)
        ? args.modifiers.filter(
            (item: unknown): item is string => typeof item === 'string',
          )
        : []
      if (!key) return null
      return formatKeyShortcut(key, modifiers)
    }
    case 'computer_click': {
      if (typeof args.element_ref === 'string' && args.element_ref) {
        return `界面元素 ${args.element_ref}`
      }
      if (
        typeof args.x === 'number' &&
        typeof args.y === 'number' &&
        !Number.isNaN(args.x) &&
        !Number.isNaN(args.y)
      ) {
        return `位置 (${args.x}, ${args.y})`
      }
      return null
    }
    case 'computer_open_app': {
      return typeof args.app === 'string' && args.app.trim()
        ? args.app.trim()
        : null
    }
    case 'computer_focus_window': {
      return typeof args.window_ref === 'string' && args.window_ref.trim()
        ? args.window_ref.trim()
        : null
    }
    case 'computer_scroll': {
      const dx = typeof args.delta_x === 'number' ? args.delta_x : 0
      const dy = typeof args.delta_y === 'number' ? args.delta_y : 0
      if (dy !== 0) return dy > 0 ? '向下滚动' : '向上滚动'
      if (dx !== 0) return dx > 0 ? '向右滚动' : '向左滚动'
      return null
    }
    default:
      return null
  }
}

// ---------------------------------------------------------------------------
// FIFO 审批队列纯操作（Floating Window 的 UI queue projection）
// ---------------------------------------------------------------------------

/** 入队：按 id 去重，追加到队尾（FIFO）。 */
export function pushApproval(
  queue: ApprovalRequest[],
  approval: ApprovalRequest,
): ApprovalRequest[] {
  return queue.some((item) => item.id === approval.id)
    ? queue
    : [...queue, approval]
}

/** 只入队 desktop 审批；sandbox 审批直接忽略（浮窗不处理）。 */
export function maybePushDesktopApproval(
  queue: ApprovalRequest[],
  approval: ApprovalRequest,
): ApprovalRequest[] {
  return isDesktopApproval(approval) ? pushApproval(queue, approval) : queue
}

/** 兼容旧名。 */
export function maybePushComputerApproval(
  queue: ApprovalRequest[],
  approval: ApprovalRequest,
): ApprovalRequest[] {
  return maybePushDesktopApproval(queue, approval)
}

/** 按 id 出队（approval.resolved / 本地 resolve 都走这里）。 */
export function removeApproval(
  queue: ApprovalRequest[],
  id: string,
): ApprovalRequest[] {
  return queue.filter((item) => item.id !== id)
}
