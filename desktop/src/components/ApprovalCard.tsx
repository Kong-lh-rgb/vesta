/** 统一审批卡片视觉：Chat 与 ApprovalsPage 均可复用。 */

import type { ReactElement } from 'react'
import type { ApprovalRequest } from '../api/types'
import {
  computerActionDescription,
  computerActionLabel,
  isDesktopApproval,
} from '../approval/computerApproval'
import { Icon } from './Icon'
import { Button } from './ui'

export interface ApprovalCardProps {
  approval: ApprovalRequest
  busy?: boolean
  onApprove: (id: string) => void
  onDeny: (id: string) => void
}

function sandboxApprovalLabel(approval: ApprovalRequest): string {
  if (['run_shell_command', 'run_command'].includes(approval.tool_name)) {
    return '执行终端命令'
  }
  if (approval.tool_name === 'http_request') return '访问外部网络'
  return '执行敏感操作'
}

function sandboxApprovalDescription(approval: ApprovalRequest): string {
  if (['run_shell_command', 'run_command'].includes(approval.tool_name)) {
    return 'Vesta 需要在本地终端执行以下命令。请确认命令内容和影响后再允许。'
  }
  if (approval.tool_name === 'http_request') {
    return 'Vesta 需要向外部服务发送网络请求。请确认目标和参数后再允许。'
  }
  return '这项操作可能修改本地环境或访问外部资源，请确认后再继续。'
}

function commandPreview(approval: ApprovalRequest): string | null {
  if (!['run_shell_command', 'run_command'].includes(approval.tool_name)) {
    return null
  }
  const command = approval.arguments?.command
  return typeof command === 'string' && command.trim() ? command.trim() : null
}

export default function ApprovalCard({
  approval,
  busy = false,
  onApprove,
  onDeny,
}: ApprovalCardProps): ReactElement {
  const desktop = isDesktopApproval(approval)
  const title = desktop
    ? computerActionLabel(approval)
    : sandboxApprovalLabel(approval)
  const description = desktop
    ? computerActionDescription(approval)
    : sandboxApprovalDescription(approval)
  const command = commandPreview(approval)
  const argsText = (() => {
    try {
      return JSON.stringify(approval.arguments, null, 2)
    } catch {
      return String(approval.arguments)
    }
  })()

  return (
    <div className="approval-card" data-testid="approval-card">
      <div className="approval-card__heading">
        <span className="approval-card__icon"><Icon name="approvals" size={17} /></span>
        <div>
          <div className="approval-card__eyebrow">需要你的确认</div>
          <div className="approval-card__title">允许“{title}”吗？</div>
          <div className="approval-card__desc">{description}</div>
        </div>
      </div>
      {command ? (
        <div className="approval-card__command">
          <span>即将执行</span>
          <code>{command}</code>
        </div>
      ) : null}
      {approval.reason ? (
        <div className="approval-card__reason">{approval.reason}</div>
      ) : null}
      {argsText ? (
        <details className="approval-card__details">
          <summary>查看技术详情</summary>
          <div className="approval-card__tech">工具：{approval.tool_name}</div>
          <pre>{argsText}</pre>
        </details>
      ) : null}
      <div className="approval-card__actions">
        <Button
          variant="danger"
          size="sm"
          disabled={busy}
          onClick={() => onDeny(approval.id)}
        >
          拒绝
        </Button>
        <Button
          variant="primary"
          size="sm"
          disabled={busy}
          onClick={() => onApprove(approval.id)}
        >
          允许执行
        </Button>
      </div>
    </div>
  )
}
