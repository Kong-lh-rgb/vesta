/** 新会话的工作入口：展示核心能力，并提供可填入输入框的示例任务。 */

import type { ReactElement } from 'react'

import { Icon, type IconName } from './Icon'

export const EXAMPLE_PROMPTS = [
  '打开备忘录，整理并写入今天的想法',
  '整理一个文件夹里的文件并生成清单',
  '创建一个每天早晨执行的信息简报',
  '调研一个主题并制定可执行的计划',
] as const

const STARTERS: ReadonlyArray<{
  title: string
  description: string
  prompt: (typeof EXAMPLE_PROMPTS)[number]
  icon: IconName
}> = [
  {
    title: '操作电脑',
    description: '打开应用、输入内容，并在关键操作前征求你的确认',
    prompt: EXAMPLE_PROMPTS[0],
    icon: 'computer',
  },
  {
    title: '整理文件',
    description: '读取、归类和生成文件，重要修改全程可见',
    prompt: EXAMPLE_PROMPTS[1],
    icon: 'file',
  },
  {
    title: '安排自动化',
    description: '把重复工作交给 Vesta 按时执行',
    prompt: EXAMPLE_PROMPTS[2],
    icon: 'automations',
  },
  {
    title: '调研与规划',
    description: '收集信息、拆解目标，并持续跟踪任务进度',
    prompt: EXAMPLE_PROMPTS[3],
    icon: 'runs',
  },
]

export default function ChatEmptyState({
  onSelectPrompt,
}: {
  onSelectPrompt: (prompt: string) => void
}): ReactElement {
  return (
    <section className="chat-empty" aria-label="开始新会话">
      <div className="chat-empty__eyebrow">
        <span className="chat-empty__mark">V</span>
        <span>新的工作空间</span>
      </div>
      <h1>今天想让 Vesta 帮你完成什么？</h1>
      <p className="chat-empty__intro">
        直接描述你想要的结果。执行过程会实时展示，需要授权的操作会先征求你的确认。
      </p>
      <div className="chat-empty__prompts">
        {STARTERS.map((starter) => (
          <button
            key={starter.prompt}
            type="button"
            aria-label={`使用示例：${starter.prompt}`}
            onClick={() => onSelectPrompt(starter.prompt)}
          >
            <span className="chat-empty__prompt-icon">
              <Icon name={starter.icon} size={17} />
            </span>
            <span className="chat-empty__prompt-copy">
              <strong>{starter.title}</strong>
              <small>{starter.description}</small>
            </span>
            <Icon name="plus" size={15} className="chat-empty__prompt-action" />
          </button>
        ))}
      </div>
      <div className="chat-empty__hint">
        <span>普通模式直接执行</span>
        <i aria-hidden="true" />
        <span>规划模式先确认方案</span>
      </div>
    </section>
  )
}
