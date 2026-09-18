import { useEffect, useRef, useState } from 'react'
import type { Conversation } from '../api/types'
import { ConfirmDialog } from './ConfirmDialog'
import { Icon } from './Icon'

const PINNED_KEY = 'vesta.pinnedConversations'

function loadPinned(): string[] {
  try {
    const raw = localStorage.getItem(PINNED_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed)
      ? parsed.filter((x): x is string => typeof x === 'string')
      : []
  } catch {
    return []
  }
}

const STATUS_META: Record<string, { label: string; tone: string }> = {
  running: { label: '工作中', tone: 'running' },
  pending: { label: '等待中', tone: 'waiting' },
  completed: { label: '已完成', tone: 'completed' },
  failed: { label: '失败', tone: 'failed' },
  cancelled: { label: '已取消', tone: 'cancelled' },
  interrupted: { label: '已停止', tone: 'failed' },
}

function relativeTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const diff = Date.now() - date.getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  return `${days}d`
}

export default function ConversationList({
  conversations,
  selectedId,
  onSelect,
  onNew,
  onRename,
  onDelete,
  statusByConversation = {},
  activityByConversation = {},
}: {
  conversations: Conversation[]
  selectedId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  /** 重命名会话（接入后端）。 */
  onRename?: (id: string, title: string) => void | Promise<void>
  /** 删除会话（接入后端）。 */
  onDelete?: (id: string) => void | Promise<void>
  /** conversationId → 最近 run 状态（Agent workspace 感：状态比消息数更重要）。 */
  statusByConversation?: Record<string, string>
  /** conversationId → 当前人类可读动作，如 “Typing in Notes”。 */
  activityByConversation?: Record<string, string>
}): React.JSX.Element {
  const [pinned, setPinned] = useState<string[]>(loadPinned)
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)

  // 点击菜单外部关闭。
  useEffect(() => {
    if (menuFor === null) return
    const onPointer = (event: MouseEvent): void => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuFor(null)
      }
    }
    document.addEventListener('mousedown', onPointer)
    return () => document.removeEventListener('mousedown', onPointer)
  }, [menuFor])

  const togglePin = (id: string): void => {
    setPinned((prev) => {
      const next = prev.includes(id)
        ? prev.filter((p) => p !== id)
        : [id, ...prev]
      try {
        localStorage.setItem(PINNED_KEY, JSON.stringify(next))
      } catch {
        /* 持久化失败不影响本次置顶 */
      }
      return next
    })
  }

  // 置顶会话排在最前。
  const ordered = [...conversations].sort((a, b) => {
    const ai = pinned.includes(a.id) ? 0 : 1
    const bi = pinned.includes(b.id) ? 0 : 1
    return ai - bi
  })
  // 第一个未置顶会话的索引（用于置顶/未置顶分界线）。
  const firstUnpinnedIndex = ordered.findIndex((c) => !pinned.includes(c.id))

  // 内联重命名状态（Electron 不实现 window.prompt，改用输入框）。
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingValue, setEditingValue] = useState('')

  const startRename = (id: string, current: string): void => {
    setEditingValue(current)
    setEditingId(id)
    setMenuFor(null)
  }

  const commitRename = (id: string, original: string): void => {
    setEditingId(null)
    const trimmed = editingValue.trim()
    if (!trimmed || trimmed === original) return
    void onRename?.(id, trimmed)
  }

  // 删除二次确认：硬删除会连带清理全部关联数据，绝不允许一次误点击触发。
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string
    title: string
  } | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const runDelete = (id: string, title: string): void => {
    setMenuFor(null)
    setDeleteTarget({ id, title })
  }

  const confirmDelete = (): void => {
    const target = deleteTarget
    if (target === null || deletingId !== null) return
    setDeletingId(target.id)
    void Promise.resolve(onDelete?.(target.id))
      .catch(() => {
        // 删除失败由调用方展示错误并保留会话；这里只负责收起菜单状态。
      })
      .finally(() => {
        setDeletingId(null)
        setDeleteTarget(null)
      })
  }

  const cancelDelete = (): void => {
    if (deletingId !== null) return
    setDeleteTarget(null)
  }

  return (
    <div className="conversation-sidebar__content">
      <div className="conversation-sidebar__top">
        <div className="conversation-sidebar__label">工作</div>
        <button className="new-conversation" type="button" onClick={onNew}>
          <Icon name="plus" size={14} />
          新建
        </button>
      </div>
      <div className="conversation-list">
        {conversations.length === 0 ? (
          <div className="conversation-list__empty">暂无对话</div>
        ) : null}
        {ordered.map((conversation, index) => {
          const status = statusByConversation[conversation.id]
          const meta = status ? STATUS_META[status] : undefined
          const activity = activityByConversation[conversation.id]
          const isPinned = pinned.includes(conversation.id)
          const showDivider = index === firstUnpinnedIndex && firstUnpinnedIndex > 0
          return (
            <div key={conversation.id} className="conversation-list__row">
              {showDivider ? (
                <div className="conversation-list__divider" aria-hidden="true" />
              ) : null}
              <div
                className={`conversation-item ${selectedId === conversation.id ? 'active' : ''}`}
              >
              <button
                type="button"
                className="conversation-item__main"
                onClick={() => onSelect(conversation.id)}
                aria-current={selectedId === conversation.id ? 'true' : undefined}
              >
                {editingId === conversation.id ? (
                  <input
                    className="conversation-item__edit"
                    value={editingValue}
                    autoFocus
                    aria-label="编辑会话标题"
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => setEditingValue(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault()
                        commitRename(conversation.id, conversation.title || '')
                      } else if (event.key === 'Escape') {
                        setEditingId(null)
                      }
                    }}
                    onBlur={() => {
                      if (editingId === conversation.id) {
                        commitRename(conversation.id, conversation.title || '')
                      }
                    }}
                  />
                ) : (
                  <span className="conversation-item__title">
                    {isPinned ? <Icon name="pin" size={11} /> : null}
                    {conversation.title || '未命名对话'}
                  </span>
                )}
                <span className="conversation-item__meta">
                  {meta ? (
                    <span
                      className={`conversation-item__status conversation-item__status--${meta.tone}`}
                    >
                      {status === 'completed' ? '✓' : meta.label}
                    </span>
                  ) : null}
                  <span>{relativeTime(conversation.updated_at)}</span>
                </span>
                {activity && ['running', 'pending'].includes(status ?? '') ? (
                  <span className="conversation-item__activity">{activity}</span>
                ) : null}
              </button>
              <button
                type="button"
                className="conversation-item__more"
                aria-label="更多操作"
                title="更多操作"
                onClick={(event) => {
                  event.stopPropagation()
                  setMenuFor((cur) => (cur === conversation.id ? null : conversation.id))
                }}
              >
                <Icon name="more" size={15} />
              </button>
              {menuFor === conversation.id ? (
                <div className="conversation-menu" ref={menuRef} role="menu">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => togglePin(conversation.id)}
                  >
                    <Icon name="pin" size={13} />
                    {isPinned ? '取消置顶' : '置顶'}
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => startRename(conversation.id, conversation.title || '')}
                  >
                    <Icon name="pencil" size={13} />
                    编辑
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className="conversation-menu__danger"
                    disabled={deletingId === conversation.id}
                    onClick={() => runDelete(conversation.id, conversation.title || '')}
                  >
                    <Icon name="trash" size={13} />
                    删除
                  </button>
                </div>
              ) : null}
              </div>
            </div>
          )
        })}
      </div>
      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除会话"
        message={
          <div className="conversation-delete-confirm">
            <p>
              将永久删除会话「{deleteTarget?.title || '未命名对话'}」，并连带清理：
            </p>
            <p className="conversation-delete-confirm__scope">
              消息与摘要、Run 记录、Task、Trace、Checkpoint、Evidence、
              审批记录、Artifact 文件与相关截图。
            </p>
            <p className="conversation-delete-confirm__warning">此操作不可恢复。</p>
          </div>
        }
        confirmLabel={deletingId !== null ? '删除中…' : '删除'}
        cancelLabel="取消"
        tone="danger"
        busy={deletingId !== null}
        onConfirm={confirmDelete}
        onCancel={cancelDelete}
      />
    </div>
  )
}
