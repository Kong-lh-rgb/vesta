// @vitest-environment happy-dom
/** ConversationList 删除会话安全确认交互测试（P0）。

验收：用户不可能通过一次误点击触发不可恢复的硬删除——
- 点“删除”只打开确认对话框，不触发 onDelete；
- 对话框明确列出连带清理范围与不可恢复警告；
- 确认后才执行删除，且 pending 期间按钮禁用防止重复请求；
- 取消不触发删除。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import type { Conversation } from '../api/types'
import ConversationList from './ConversationList'

afterEach(() => {
  cleanup()
})

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: 'conv-1',
    title: 'Desktop redesign',
    message_count: 3,
    created_at: '2026-08-20T00:00:00+00:00',
    updated_at: '2026-08-20T01:00:00+00:00',
    ...overrides,
  }
}

function openDeleteMenu(): void {
  fireEvent.click(screen.getByRole('button', { name: '更多操作' }))
  fireEvent.click(screen.getByRole('menuitem', { name: /删除/ }))
}

describe('ConversationList 删除确认', () => {
  it('点删除只打开确认对话框，不立即触发 onDelete', () => {
    const onDelete = vi.fn()
    render(
      <ConversationList
        conversations={[makeConversation()]}
        selectedId="conv-1"
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={onDelete}
      />,
    )

    openDeleteMenu()

    expect(onDelete).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog', { name: '删除会话' })).toBeTruthy()
  })

  it('确认对话框列出连带删除范围与不可恢复警告', () => {
    render(
      <ConversationList
        conversations={[makeConversation()]}
        selectedId="conv-1"
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={() => {}}
      />,
    )

    openDeleteMenu()

    const dialog = screen.getByRole('dialog', { name: '删除会话' })
    const text = dialog.textContent ?? ''
    expect(text).toContain('Desktop redesign')
    expect(text).toContain('Run')
    expect(text).toContain('Task')
    expect(text).toContain('Trace')
    expect(text).toContain('Checkpoint')
    expect(text).toContain('Evidence')
    expect(text).toContain('审批')
    expect(text).toContain('Artifact')
    expect(text).toContain('截图')
    expect(text).toContain('不可恢复')
  })

  it('确认后触发一次 onDelete；pending 期间确认按钮禁用', async () => {
    let release: (() => void) | undefined
    const onDelete = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          release = resolve
        }),
    )
    render(
      <ConversationList
        conversations={[makeConversation()]}
        selectedId="conv-1"
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={onDelete}
      />,
    )

    openDeleteMenu()
    const confirm = screen.getByRole('button', { name: '删除' })
    await act(async () => {
      fireEvent.click(confirm)
    })

    expect(onDelete).toHaveBeenCalledTimes(1)
    // pending 期间按钮禁用（防重复请求）。
    expect(
      (screen.getByRole('button', { name: '删除中…' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true)
    expect(
      (screen.getByRole('button', { name: '取消' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true)

    await act(async () => {
      release?.()
    })
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull()
    })
  })

  it('取消不触发 onDelete 并关闭对话框', () => {
    const onDelete = vi.fn()
    render(
      <ConversationList
        conversations={[makeConversation()]}
        selectedId="conv-1"
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={onDelete}
      />,
    )

    openDeleteMenu()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))

    expect(onDelete).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('删除失败后对话框收起（会话保留由调用方负责）', async () => {
    const onDelete = vi.fn(() => Promise.reject(new Error('backend down')))
    render(
      <ConversationList
        conversations={[makeConversation()]}
        selectedId="conv-1"
        onSelect={() => {}}
        onNew={() => {}}
        onDelete={onDelete}
      />,
    )

    openDeleteMenu()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '删除' }))
    })

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull()
    })
    // 对话框关闭后可以重新发起删除（未被失败状态卡死）。
    openDeleteMenu()
    expect(screen.getByRole('dialog', { name: '删除会话' })).toBeTruthy()
  })
})
