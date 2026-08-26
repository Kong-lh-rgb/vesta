# Vesta 面试复习记录

> 用途：记录一问一答中已经确认的关键答案、追问、源码证据和易错点。
> 原则：只保留能够用自己的语言解释，并且与当前代码实现一致的内容。

## 使用方法

1. 每轮先脱稿回答，不追求术语完整。
2. 回答不清楚时，再定位源码、测试或评测报告。
3. 确认后的答案整理为“结论—实现—取舍—不足”四部分。
4. 对尚未确认的内容标记为待复习，不把猜测写成事实。

## 已确认的核心答案

后续按问答结果持续补充。

## 问答记录

### Q1：Vesta 解决了什么问题？为什么普通聊天机器人或单轮 Tool Calling 不够？

- 状态：已掌握
- 你的原始回答摘要：Vesta 面向长期任务，尝试解决上下文遗忘、回答不连贯以及单轮工具调用无法完成未知长度任务的问题；同时认为单次任务成功不应该直接沉淀为 Skill，只有短期内重复完成且具有复用价值的任务，才适合从真实经验中提炼 Skill。
- 第一次作答的亮点：
  - 抓住了“长期任务不是单轮问答”的核心差异。
  - 知道长期任务通常需要多轮模型—工具循环，而不是一次 Tool Calling。
  - 对 Skill Learning 有自己的设计判断：单个成功样本不等于可复用经验，应该基于多个 Completed Task 和真实 Trace 判断重复模式。
- 需要修正：
  - “回答不连贯”过于宽泛，应具体为上下文窗口受限、工具结果膨胀、跨 Run 状态丢失和中断后无法安全恢复。
  - 不要把 Skill Learning 放在问题定义的最前面。先讲可持续执行与恢复，再讲 Memory 和 Skill Learning。
  - “用户目标不确定”不准确。更准确的是：目标可以明确，但执行路径、工具轮数、失败次数和人工审批次数无法预先确定。
  - 不必把实现限定为 ReAct。可以表述为“持续的模型—工具迭代循环”，因为 Vesta 还包含状态、预算、恢复和审批等 Runtime 能力。
- 二答结构：
  1. 普通聊天应用的问题：一次请求内生成答案，缺乏跨 Run 的任务状态和安全恢复边界。
  2. 长任务的工程问题：执行路径不确定、工具结果增长、可能失败/暂停/重启、外部副作用不能随意重试。
  3. Vesta 的解决方案：Agent Runtime 管理 Run/Task/Checkpoint，Context 治理控制窗口，Memory 跨会话保留信息，Skill Learning 从重复完成任务中提炼经验，并用 Trace/Eval 验证。
  4. 一句话区别：Vesta 不是给模型增加几个工具，而是为 Agent 提供能够持续执行、恢复、记忆、学习和评测的运行系统。
- 你的第二次回答摘要：普通聊天机器人主要围绕一次请求生成答案；长任务即使目标明确，执行路径、工具轮数、失败和审批次数仍无法预先确定。执行过程中还会遇到上下文窗口受限、工具结果膨胀、跨 Run 状态丢失和中断后难以恢复。Vesta 会为模型构建包含对话、工具、Skill 和长期记忆的上下文，并基于模型窗口设置预算，在达到阈值时处理工具结果、历史工具轮和旧对话摘要。
- 第二次作答的进步：
  - 已经区分了“目标明确”和“执行路径不确定”。
  - 能列举长任务中的具体工程问题，不再只说“回答不连贯”。
  - 开始用 Context Budget 和分阶段压缩解释实现，而不是只列功能名称。
- 第二次作答需要继续修正：
  - 多次 Tool Calling 不是 Vesta 与普通 Agent 的根本边界，普通 ReAct Agent 同样可以循环调用工具。
  - Context 不是只在每个 Run 开始时构建，而是在每次模型请求前准备和预算。
  - 不能笼统说“工具结果移除”：先压缩/截断旧 Tool Result，必要时再成组裁剪完整历史 Tool Round，以维护 assistant tool call 与 tool result 的协议配对。
  - 最终总结不能只说“长期可运行”，应包含持续执行、恢复、记忆、学习和评测。
- Q1.1 回答摘要：认为 LangChain 对 Agent 做了较厚的封装，错误排查不够直接；Vesta 可以提供更细粒度的执行 Trace。普通模型—工具循环通常只服务于当前 Run，而 Vesta 在每次模型请求前都会重新构建和治理上下文。
- Q1.1 答对的部分：
  - 可观测性是 Harness 与简单工具循环的重要区别。
  - 已修正为“每次模型请求前准备 Context”，不再说只在 Run 开始时构建。
- Q1.1 必须修正：
  - 不要把“LangChain 比较厚重”作为主要论点。LangChain/LangGraph 是开发框架，Vesta 是围绕运行生命周期、状态、恢复和评测建立的系统，二者关注层次不同，也可以组合使用。
  - 不要说 Vesta 记录“模型思考了什么”。Vesta 主动丢弃 Provider 原始 reasoning，不保存或展示隐藏思维链；Trace 记录的是结构化、可验证的执行事实，如模型调用、Tool Call/Result、审批、Checkpoint、Stop Reason、Token 和耗时。
  - 回答仍缺少最关键的持久化与恢复语义：普通循环一般只保存内存中的 messages；Vesta 分离 Run、Task、Checkpoint，并区分已完成工具结果与状态不确定的 pending tool call，避免恢复时盲目重复副作用。
  - 还可以补充长期能力：Memory 跨会话保留事实，Skill 从多个 Completed Task 的真实 Trace 中提炼，Eval 用事实断言和重复运行衡量稳定性。
- Q1.2 场景回答摘要：Checkpoint 会记录当前执行进度、模型发起的工具调用以及已经拿到的工具结果。进程崩溃时，如果工具已经执行但结果尚未持久化，系统无法判断外部副作用是否发生，因此既不能视为未执行，也不能视为已确认完成，更不能直接重试。
- Q1.2 关键修正：
  - 更准确的术语不是把“工具调用视为暂停”，而是旧 Run/Checkpoint 进入 `INTERRUPTED`，该调用保留在 `pending_tool_calls` 中，执行结果标记为 uncertain。
  - 恢复不是让旧进程从某一行代码继续。系统会在同一个 Conversation 下创建新的 Recovery Run，旧 Run 保持 `INTERRUPTED` 作为历史事实。
  - `completed_tool_results` 可以作为已完成证据继续使用；`pending_tool_calls` 必须先核对 Trace 和外部实际状态。
  - 对邮件、支付等有副作用的未决工具禁止自动重试。优先查询外部状态或使用幂等键；无法验证时询问用户或明确报告不确定性。
- 确认后的答案：普通聊天应用或简单 Agent 通常只维护当前调用中的消息和模型—工具循环。长程任务的目标可以明确，但执行路径、工具轮数、失败、人工审批和运行时间无法预先确定；同时还会遇到上下文膨胀、进程中断、外部副作用和跨 Run 状态丢失。Vesta 因此不只提供 Tool Calling，而是用 Run 管理一次执行生命周期，用 Task 保存跨 Run 的长期目标，用 Checkpoint 保存可恢复边界；每次模型请求前进行 Context Budget 与分阶段压缩，并通过 Memory、Skill Learning、Trace 和 Eval 提供跨会话记忆、经验复用、可观测性与验证闭环。它与普通 Agent 的根本区别是：Vesta 是让 Agent 能够持续执行、安全恢复、记忆、学习和被评测的 Runtime/Harness，而不只是一个循环调用工具的程序。
- 可能追问：
  - 一个能够循环调用 10 次工具的 ReAct Agent，为什么仍然不等于 Vesta？
  - 如果邮件已经发出，但进程在保存 Tool Result 前崩溃，恢复时应该怎么处理？
  - Run、Task、Checkpoint 为什么必须分开？
  - “安全恢复”具体如何避免重复执行有副作用的工具？
  - Memory 和 Skill 有什么区别？
  - 为什么一个 Completed Task 不足以生成 Skill？
- 源码证据：
  - `README.md`：总体架构与 Core Concepts。
  - `backend/app/run/manager.py`：Run 生命周期与恢复入口。
  - `backend/app/context/manager.py`：上下文预算和压缩。
  - `backend/app/skill_learning/service.py`：多任务经验到 Candidate 的学习流程。

## 易混淆与易答错点

- 不要把“可以多次 Tool Calling”作为 Vesta 的核心差异，普通 ReAct Agent 也能做到。
- 不要说 Trace 保存模型隐藏思维链；Vesta 只保存结构化、可验证的执行事件。
- Context 在每次模型请求前准备，不是只在 Run 开始时构建。
- pending Tool Call 表示执行结果不确定，不等于失败或未执行；副作用工具禁止盲目重试。
- Recovery 会创建新 Run；旧 Run 保持 `INTERRUPTED`，不会从原进程的某行代码恢复。

## 待回看源码

- `backend/app/checkpoint/context.py`：恢复证据与 pending/completed 语义。
- `backend/app/run/manager.py`：`interrupt()`、`recover()` 与新旧 Run 关系。

## 后续问题

### Q2：Run、Task、Checkpoint 为什么要分成三个对象？

- 状态：已掌握
- 你的原始回答摘要：Run 表示一次执行，其中包含多个 Step；Task 在用户发起复杂目标时记录任务状态和里程碑，Agent 可以通过任务工具创建和更新；Checkpoint 保存当前执行进度，供中断后恢复。在“完成软件项目”的例子里，每次执行对应 Run，Task 持续记录整个项目的进度，Checkpoint 用于恢复。
- 答对的部分：
  - 已经抓住三种不同时间尺度：一次执行、跨执行目标、执行内恢复边界。
  - 知道 Task 可以通过工具显式创建和更新步骤。
  - 知道恢复依赖 Checkpoint，而不是只依赖对话历史。
- 需要修正：
  - Run 是一次 execution attempt，不严格等于一次用户提问；手动输入、Automation 和 Recovery 都可以产生 Run。
  - Step 更准确地表示主 Agent Loop 的一次迭代，通常包含一次主模型响应以及可能的工具执行；Context Summary、Reflection 等辅助模型调用不一定各自成为 Agent Step。
  - Task 保存目标、约束、步骤、状态和关键事实，不保存完整执行过程；“实际发生过什么”属于 Trace。
  - Checkpoint 是一次 Run 的最小可恢复状态，包含 phase、step、pending Tool Calls 和 completed Tool Results，不是完整执行日志。
  - 三者分离的根本原因不是“状态无法枚举”，而是生命周期、关系和查询目的不同：一个 Task 可跨多个 Run，每个 Run 在当前实现中有一条不断更新的 Checkpoint 记录，同时还有独立 Trace 事件。
- 场景数量：整个“完成软件项目”通常是 1 个 Task。初始执行、第一次恢复、第二次恢复是 3 个 Run；前两个 Run 终态为 `INTERRUPTED`，第三个 Run 完成后为 `COMPLETED`。当前实现按 Run 创建一条 Checkpoint 记录，并在模型请求前、工具执行前和工具结果返回后持续更新，因此这里会有 3 条 Run 对应的 Checkpoint 记录，其中前两条保存中断恢复证据。
- 为什么旧 Run 不能重新改回 RUNNING：Run 表示一次不可篡改的 execution attempt。中断说明这次尝试已经结束，重新启动会改变历史事实、混淆 Trace/Usage/审计，并让副作用工具的归属不清。恢复应创建新 Run，通过 `recovered_from_run_id` 连接旧 Run；旧 Run 永久保留 `INTERRUPTED`。
- 你的补充回答：整个软件项目只有 1 个 Task；需求分析、第一次恢复后完成后端、第二次恢复后完成前端和测试分别属于 3 个 Run；Checkpoint 与 Run 对应。前两个 Run 因用户暂停和进程退出进入中断终态，第三个 Run 完成。旧 Run 如果直接重新进入 RUNNING，可能重复执行结果不确定的工具，或者错误跳过未完成步骤，破坏执行连续性。
- 确认后的答案：Run、Task、Checkpoint 是三个正交的领域对象。Task 是业务目标的权威状态，保存跨 Run 的目标、约束、Steps、进度和关键事实；Run 是一次 execution attempt 的生命周期索引，回答“这次执行现在处于什么状态”；Checkpoint 是该 Run 的最小可恢复状态，回答“中断后有哪些已确认事实和未决调用”。一个 Task 可以关联多个 Run，当前实现为每个 Run 创建一条持续更新的 Checkpoint 记录。恢复必须创建新 Run，旧 Run 永久保留 `INTERRUPTED`，既避免对不确定副作用的盲目重试，也保留准确的 Trace、Usage、审计和恢复关系。
- 可能追问：
  - Run 和 Trace 有什么区别？
  - 为什么 Checkpoint 不直接保存完整 Conversation？
  - Recovery Run 再次中断时，旧 Checkpoint 如何处理？
- 源码证据：
  - `backend/app/run/models.py`：Run 是 execution attempt，`INTERRUPTED` 为终态。
  - `backend/app/task/models.py`：Task 保存跨 Run 的目标、约束、步骤和关键事实。
  - `backend/app/checkpoint/models.py`：Checkpoint 是每个 Run 的最小可恢复状态。
- `backend/app/checkpoint/store.py`：同一 Run 的 Checkpoint 在关键边界持续更新。

### Q3：Checkpoint 为什么要在模型请求前、工具执行前和每个工具结果返回后分别更新？

- 状态：已掌握
- 你的原始回答摘要：Checkpoint 是恢复边界，因此必须在模型请求前记录阶段，在工具执行前记录将要执行的全部工具，在每个工具结果返回后记录成功/失败和结果。如果只在整个工具批次结束后保存，中途崩溃就无法区分哪些工具已经完成。A/B/C 并行执行且 A 已返回时，Checkpoint 中 pending 是 B、C，completed 是 A；A 必须立即保存，避免恢复后重复执行。
- 答对的部分：
  - 正确判断 `pending_tool_calls = [B, C]`，`completed_tool_results = [A]`。
  - 理解了工具执行前必须先持久化调用意图，结果返回后必须逐个提交完成事实。
  - 理解了等待整个批次结束会扩大不确定窗口，并导致已完成工具被错误重试。
- 需要修正：模型请求前的 Checkpoint 不保存完整“构建后的上下文”。它记录当前 `step`、把 phase 更新为 `MODEL_REQUEST`，并清空上一工具批次的 pending 集合；这样恢复时可以确认崩溃发生在模型请求阶段，而不是带副作用的工具执行阶段。Conversation、Summary、Task、Memory 等有各自的权威存储。
- 确认后的答案：Checkpoint 在这里类似工具执行的 write-ahead journal。`before_model` 记录当前主循环 Step 已进入模型请求阶段；`before_tools` 在产生任何外部副作用前先持久化模型给出的全部 Tool Calls；`complete_tool` 在每个结果返回时，原子地把对应调用从 pending 移到 completed。若 A/B/C 并行执行时 A 已返回而进程崩溃，恢复证据应是 A 已确认完成、B/C 结果不确定。逐个提交可以缩小不确定窗口，避免 A 被重复执行；执行前写入可以保证即使进程在调用工具后立即崩溃，系统仍知道哪些副作用可能已经发生。
- 可能追问：
  - 为什么不能只依赖 Trace 恢复？
  - `complete_tool` 为什么需要事务？
  - 模型请求阶段崩溃是否可以安全重试？
- 源码证据：
  - `backend/app/checkpoint/store.py`：`before_model()`、`before_tools()`、`complete_tool()`。
  - `backend/app/checkpoint/models.py`：Checkpoint Phase、pending 与 completed 字段。

### Q4：为什么 Context 压缩必须按 Tool Result、完整 Tool Round、Rolling Summary 的顺序进行？

- 状态：已掌握
- 你的原始回答摘要：先处理相对容易膨胀的 Tool Result；如果仍超限，再成组裁剪 Tool Call 与 Tool Result 对应的完整 Tool Round，避免协议不完整；仍超限时才调用模型生成 Rolling Summary，因为摘要有额外模型成本。摘要必须保留关键事实、用户目标和任务约束，默认保护最近两轮工具结果。
- 答对的部分：
  - 正确理解了 Tool Call 与 Tool Result 的协议配对，不能只删除其中一侧。
  - 正确理解了 Rolling Summary 会增加模型调用、Token、延迟和成本。
  - 正确指出摘要必须保留目标、约束和关键事实。
  - “默认保护最近两轮 Tool Round”与当前配置一致。
- 必须修正：
  - Tool Result 不是因为“不重要”才优先处理，用户问题也没有预先隐含工具返回的事实。工具结果通常是最权威的外部证据。
  - 优先处理 Tool Result 是因为原始输出常常体积最大，含有重复字段、日志或与目标无关的噪声，可以先在保留关键证据的前提下做有界压缩。
  - Rolling Summary 放最后不仅因为成本，还因为它是有损、可能失败且存在语义漂移的模型变换；能通过确定性的工具整理达到预算时，就不应过早总结对话。
- 确认后的答案：Vesta 先独立核算 Tool Result Budget，因为工具原始输出往往是上下文膨胀的主要来源，可以先压缩冗余输出而保留关键证据。若仍超限，再删除旧的完整 Tool Round，保证 assistant 的 Tool Calls 和对应 Tool Results 始终协议配对。只有工具层整理后请求仍达到 Context Trigger，或未摘要的对话块过多，才对旧的持久化历史生成 Rolling Summary，因为摘要会产生模型成本、延迟、失败和语义损失。压缩只作用于符合条件的历史前缀，当前 Run 新增消息保持完整；原始 Conversation 不被改写；Task、Memory、运行环境、Active Skill 和 Recovery Context 等临时上下文不会进入摘要，而是在每次请求时重新注入。默认还会保护最近 2 个完整 Tool Round。
- 可能追问：
  - 为什么原始 Conversation 不能直接被摘要覆盖？
  - Summary 失败时系统如何降级？
  - 为什么要同时设置 Trigger 和 Target？
- 源码证据：
  - `backend/app/context/manager.py`：历史/当前消息边界与分阶段压缩。
  - `backend/app/context/reducers/tool.py`：Tool Result 压缩和完整 Tool Round 裁剪。
  - `backend/app/context/reducers/conversation.py`：Rolling Summary 与最近工具轮保护。
  - `backend/app/context/config.py`：默认保留最近 2 个 Tool Round。

### Q5：Context Budget 为什么同时需要 Trigger 和 Target？

- 状态：已掌握
- 你的原始回答摘要：设置 Trigger 可以避免上下文无限膨胀导致注意力分散和请求成本上升；设置更低的 Target 可以让一次压缩真正产生效果。如果 Trigger 和 Target 都是 80%，新增少量内容后会再次触发摘要，产生反复压缩。不能等到模型最大窗口才处理，否则每轮都携带巨大上下文；压缩后的空间留给后续内容。
- 答对的部分：
  - 正确指出上下文过大同时影响质量和成本。
  - 正确识别 Trigger=Target 会造成压缩抖动和重复模型摘要。
  - 正确理解不能把最大 Context Window 当作日常工作水位。
- 需要修正：Target 更低的主要目的不是防止关键内容被压掉。关键信息由历史/当前边界、Task/Memory/Skill 重注入、最近 Tool Round 保护和 Summary Schema 等不变量保证；Trigger 与 Target 拉开距离是为了形成滞回区间、摊薄一次压缩成本并为后续增长留出 Headroom。
- 预算公式：`input_budget = context_window - reserved_output_tokens - safety_margin_tokens`。`reserved_output_tokens` 为模型本次生成回答或 Tool Calls 预留空间，避免输入虽然能放入窗口但模型没有输出余量；`safety_margin_tokens` 吸收 Token 估算误差、不同 Provider 分词差异、消息格式和边界开销。非 OpenAI 模型还会使用保守估算系数避免低估。
- 确认后的答案：Trigger 表示进入压缩流程的水位，Target 表示压缩完成后希望回落到的工作水位。两者分离形成滞回控制：请求达到 Trigger 后一次性压缩到更低的 Target，使接下来若干轮可以继续加入用户消息、Tool Result、Task/Memory/Skill 等上下文，而不会每轮重复摘要。系统不会使用完整模型窗口作为输入预算，而是先扣除输出预留和安全边界；同时用 preferred working budget 控制日常成本与延迟，模型窗口只作为最终硬保护。
- 可能追问：
  - `input_budget`、`working_input_budget` 和模型最大窗口有什么区别？
  - 为什么非 OpenAI 模型需要保守 Token 系数？
  - Tool Schema 是否计入输入估算？
- 源码证据：
  - `backend/app/context/budget.py`：输入预算、Trigger、Target 和 Tool Result Budget 计算。
  - `backend/app/context/config.py`：硬保护与日常工作预算配置。
  - `backend/app/context/tokens.py`：消息、Tool Schema 与 Provider 保守系数。
- 快速计算确认：模型窗口 128,000、输出预留 16,000、安全边界 4,096 时，`input_budget = 107,904`。不能把 128,000 全部分给输入，因为模型还需要输出回答或 Tool Calls，同时必须吸收 Token 估算误差；否则请求可能直接超过 Provider 窗口，而不只是回答质量下降。

### Q6：Core Memory 和 Ordinary Memory 为什么要分层？

- 状态：已掌握
- 你的原始回答摘要：Core Memory 保存用户身份、重要信息和长期关键约束，因此应持续存在于上下文中。Ordinary Memory 用于保存体量更大、不是每次都需要的历史信息，按需读取可以节省 Token。长期 Python 编码偏好适合 Core，三个月前的数据库选型分析适合 Ordinary。模型可以使用内置 Memory 工具读取普通记忆正文，短期信息不应写入长期记忆。
- 答对的部分：
  - 正确区分稳定偏好与按需历史知识。
  - 正确理解 Ordinary Memory 不应把全部正文注入每次请求。
  - 知道模型通过工具主动读取 Ordinary Memory。
- 需要修正：
  - Ordinary Memory 不等于重要性低。数据库选型结论可能非常重要，只是并非每个请求都相关；分层依据是访问频率、相关性、体积和上下文成本。
  - 当前设计不是自动向量检索全部正文。系统注入轻量 Memory Index/Recall Cue，模型判断相关 `memory_id` 后调用 `memory_read` 获取完整内容，也可以使用 `memory_list` 查看条目。
  - “不应写入长期记忆”还应包含：临时请求、一次性 Task 进度、未经确认的推断、原始大段 Tool Output、重复信息、应属于 Skill 的通用操作流程，以及没有长期价值的闲聊。
- 确认后的答案：Core Memory 是每轮都值得模型知道的、精炼且稳定的用户级事实与偏好，例如身份、长期表达偏好和全局工作约束，因此常驻请求上下文。Ordinary Memory 保存跨会话仍有价值、但只在特定主题下相关的事实、决定和背景，例如某次数据库选型的结论；请求中只注入包含 ID、标题/摘要和 Recall Cue 的轻量索引，模型判断相关后再通过 `memory_read` 按 ID 获取正文。这样同时保证关键约束始终可见，又避免所有历史正文挤占 Context Budget。长期记忆只保存稳定、可复用、可确认的信息；短期进度属于 Task，通用操作经验属于 Skill，原始执行过程属于 Trace。
- 可能追问：
  - Core Memory 为什么也需要容量边界？
  - Memory Index 是否等同于向量数据库？
  - Ordinary Memory 与 Task、Skill、Trace 分别有什么边界？
- 源码证据：
  - `backend/app/memory/core.py`：Core Entry 与有界更新。
  - `backend/app/memory/index.py`：Ordinary Memory 的轻量索引。
  - `backend/app/memory/tools.py`：`memory_read`、`memory_list` 与写入工具。
  - `backend/app/memory/manager.py`：Memory 领域操作和容量约束。

### Q7：Post-Run Reflection 为什么需要 revision 乐观并发控制？

- 状态：已掌握
- 你的原始回答：不清楚，需要回看实现。
- 问题本质：Post-Run Reflection 是后台慢任务。它读取某条 Memory 后要经过一次模型决策，在这段时间内别的 Run 可能已经更新同一条 Memory。如果旧 Reflection 最后无条件写入，就会发生 lost update：基于 revision=3 生成的旧内容覆盖 revision=4 的新事实。
- 当前处理流程：
  1. 主 Run 成功调用 `memory_read` 时，记录该条 Memory 当时的 revision。
  2. Reflection 若返回 UPDATE，只允许更新当前 Run 实际读取过的 Memory。
  3. 写入时传入 `expected_revision`。Store 在短临界区内重新读取当前记录并比较版本。
  4. 如果期望 3、当前已经是 4，则抛出 `revision conflict`，不写文件、不重建错误索引，也不覆盖 revision=4。
  5. Runtime 发出 `MEMORY_REFLECTION_FAILED`，`mutation_applied=false`；主 AgentResult 已经完成，不会被后台 Reflection 失败反向改成失败。
- 为什么当前不自动重试：同一个 Proposal 是根据 revision=3 的旧正文生成的，原样重试仍然语义过期。安全做法是放弃本次 mutation；如果确实需要重试，必须重新读取 revision=4 并重新执行 Reflection，而不是重复提交旧 Proposal。当前实现选择失败隔离，等待后续 Run 产生新证据。
- 为什么使用乐观并发：Reflection 模型调用耗时远大于实际文件 mutation，冲突相对少见。如果在“读取—调用模型—写入”的整个过程持有全局锁，会长期阻塞其他 Run 的 Memory 读写。Vesta 允许并发读取和模型推理，只在最终 revision 检查、写文件和重建索引时持有短 mutation lock。
- 用户追问：A 的过期 Proposal 被拒绝后，其中总结出的新内容没有写入，这是否也是一种“丢失”？
- 取舍说明：
  - 从信息沉淀角度看，A 的 Proposal 确实可能暂时没有进入 Ordinary Memory，这是当前“安全拒绝陈旧写入”的代价。
  - 但它与并发控制术语中的 lost update 不同。lost update 指 B 已成功提交的 revision=4 被 A 基于 revision=3 的整段旧正文静默覆盖；revision check 防止的是这种已提交新状态被破坏。
  - A 的主 Run、Conversation、Trace 和 Reflection 失败事件仍然存在，丢弃的是这一次后台 Memory mutation，不是主任务结果。Ordinary Reflection 本身是 best-effort housekeeping，因此当前实现优先保证已提交 Memory 不被陈旧 Proposal 破坏。
  - 若希望同时保留 A 的新信息，不能原样重试旧 Proposal。可在冲突后重新读取 revision=4，把 A 的 Run 证据与最新正文一起重新执行一次 Reflection/Rebase，并使用 `expected_revision=4` 再提交；应设置有界重试，防止高并发下活锁和额外模型成本。
  - 进一步方案包括让模型生成字段级 Patch/追加事实而不是整段替换，或使用 append-only Memory Event Log 后异步合并；这些方案合并能力更强，但复杂度、去重和冲突语义也更高。
- 你的复述：后台 Reflection 较慢；在它执行期间，另一个 Run 可能根据用户最新要求更新长期记忆。如果没有乐观锁，旧 Reflection 返回后会覆盖用户的新要求。Vesta 因此使用 revision 检查；冲突时记录失败，不提交旧写入。不会在整个 Reflection 期间持有长时间全局锁，因为模型调用很慢，会阻塞其他 Run 的 Memory 写入。
- 术语确认：lost update 指 Run B 已经提交的新状态，被后到达但基于旧 revision 的 Run A 静默覆盖，导致 B 的更新消失。revision conflict rejection 则表示 A 的旧 Proposal 从未提交，B 的新状态得到保留；A 的新信息可能延迟沉淀，但不会破坏已提交事实。
- 确认后的答案：Post-Run Reflection 是后台慢任务，读取 Memory 到最终写入之间存在并发窗口。Vesta 记录主 Run 实际读取到的 revision，并在 UPDATE 时以 `expected_revision` 做 compare-and-set；若当前 revision 已变化，则拒绝旧 Proposal、发出失败事件且不影响主 Run。这样防止陈旧 Reflection 覆盖用户在后续 Run 中已经提交的新事实。系统只在最终检查版本、写文件和重建索引时持有短 mutation lock，不在模型调用期间持有全局锁，从而兼顾并发吞吐与一致性。
- 可能追问：
  - 既然是乐观并发，为什么最终写入阶段仍需要短锁？
  - CREATE 如何避免多个 Run 同时突破容量上限？
  - Reflection 失败为什么不能影响已经完成的主 Run？
- 源码证据：
  - `backend/app/agent/runtime.py`：记录 recalled revision、应用 UPDATE、隔离失败事件。
  - `backend/app/memory/manager.py`：`update_if_revision()` 与短 mutation guard。
  - `backend/app/memory/store.py`：比较 expected/current revision 并递增版本。
  - `backend/tests/offline/memory/test_memory_reflection.py`：并发更新后拒绝过期 Reflection 的回归测试。

### Q8：为什么 Memory Reflection 放在 Post-Run 后台，而不放进主 Run 的完成路径？

- 状态：已掌握
- 你的原始回答摘要：Reflection 失败不影响主 Run，Run 仍标记成功。把 Reflection 放后台可以避免慢模型阻塞主 Agent，并允许使用独立模型配置。风险是后台执行较慢时可能与后续 Run 的 Memory 更新发生 revision conflict。Ordinary Reflection 当前允许 CREATE、UPDATE 或什么都不做；不是每个成功 Run 都需要 Reflection，例如“你好”会被过滤。
- 答对的部分：
  - 正确理解 Reflection 是 best-effort housekeeping，不属于主任务成功条件。
  - 正确指出后台执行降低用户等待时间，并允许使用独立 Provider/Model 配置。
  - 正确识别 eventual consistency 和 revision conflict 风险。
  - 正确说出 Ordinary Reflection 的 `NONE / CREATE / UPDATE` 三种决策。
- Gate 的准确规则：确定性小聊、能力列表查询和天气/时间等临时查询跳过；出现长期信号、当前 Run 读取过 Memory，或规则无法确定时保留 Reflection。Gate 采用保守策略：只跳过明确无长期价值的窄场景，不确定时交给模型做 `NONE` 判断。
- 额外工程风险：当前 PostRunProcessor 是进程内 asyncio 后台任务管理器，不是持久化分布式队列。处理器关闭或并发饱和时 Job 可能被丢弃；应用关闭只做有界 drain，超时会取消；进程崩溃也可能导致尚未完成的 Reflection 丢失。因此普通 Memory Reflection 只能承诺最终尽力沉淀，不能承诺 exactly-once。
- 确认后的答案：主 Agent 在 Checkpoint 和完成事件落定后就结束关键路径；Memory Reflection 只负责从已完成 Run 中提取可能具有长期价值的信息，因此它的超时、非法 JSON、容量不足或 revision conflict 都不应把用户已完成的任务改成失败。后台执行降低响应延迟，并允许 Reflection 独立配置模型、Token、温度和超时。代价是记忆最终一致、可能冲突或因进程退出/队列饱和而丢失 Job。系统用确定性 Gate 跳过明确的小聊、能力查询和临时查询；对长期信号、读取过 Memory 或不确定场景才调用 Reflector，最终只允许 `NONE / CREATE / UPDATE`。Ordinary Memory 的归档由独立 Maintenance 负责，不是 Reflection 的 REMOVE。
- 可能追问：
  - 如果业务要求 Reflection 必须可靠执行，架构应如何改造？
  - 为什么 Gate 不应该激进过滤所有短消息？
  - Memory Maintenance 与 Reflection 的职责边界是什么？
- 源码证据：
  - `backend/app/agent/post_run_processor.py`：后台任务提交、并发上限和有界关闭。
  - `backend/app/memory/reflection_gate.py`：确定性保守 Gate。
  - `backend/app/agent/runtime.py`：关键路径结束与后台 Reflection 调度。
  - `backend/app/memory/reflection_models.py`：`NONE / CREATE / UPDATE` 决策。

### Q9：为什么一个 Completed Task 不能直接生成 Skill？

- 状态：已掌握
- 你的原始回答摘要：Skill 应模拟人类经验沉淀，偶尔完成一次任务没有形成经验的价值，只有重复执行且确实具有复用价值的任务才值得沉淀。多个 Completed Task 先聚类；仅看任务描述和最终答案存在歧义，必须读取相关 Run 的 Trace，观察工具调用、错误修正、任务状态变化和完成过程。Trace Selector 以 Task 状态更新为锚点，选择锚点之间或锚点附近的 Agent Steps 作为蒸馏证据；最终 Candidate 还要经过 Human Gate 才成为正式 Skill。
- 答对的部分：
  - 形成了清晰的产品判断：一次偶然成功不等于稳定、可复用的经验。
  - 正确区分了 Pattern Mining 与后续 Trace Evidence/Distillation 两阶段。
  - 对 Trace Selector 的 Task Update Anchor、跨 Step/跨 Run 区间选择理解准确。
  - 正确理解 Human Gate 是正式发布前的质量与控制边界。
- 需要修正：
  - Task 不记录完整执行过程，只记录目标、约束、Steps、状态、关键事实和关联 `run_ids`；完整过程在每个 Run 的 Trace 中。
  - 不要说 Trace 保存“模型怎么思考”。Evidence 只消费结构化可观察事件：工具序列、失败结果、成功的 Task 变更和 Agent 完成/失败证据。
  - “短期内高频”是合理的产品解释，但当前 V1 没有显式时间窗口过滤。当前默认累计 20 个新的 Completed Task 才扫描，Cluster 至少 3 个任务；频率只是下限，不是生成 Skill 的唯一条件。
- 当前准确流程：
  1. Watermark 累积新的 Completed Task；达到 batch size 后把一批任务移入 inflight。
  2. Pattern Miner 只读取轻量 TaskCard，寻找可复用的相似任务 Cluster，不读取完整 Trace，也不直接生成 Skill。
  3. 对 Cluster 内每个 Task，根据 `run_ids` 加载 Trace；TaskTraceSelector 只以成功更新当前 Task 的 `task_update` 为 Anchor，构建相关 Agent Step 区间。
  4. Evidence Builder 从选中事件中提取工具序列、失败修正、Task 变更和完成证据；无 Trace 时降级为 Task-only evidence。
  5. Distiller 综合多个任务证据、现有 Skill Catalog 和待审核 Candidate，判断 `CREATE / UPDATE / NONE`，并产出 Procedure、Pitfall 等候选内容。
  6. Candidate 进入 PENDING；只有 Human Gate accept 后才写入正式 Skill，reject 则保留拒绝事实。
- 为什么需要 Human Gate：Skill 会在未来相关任务中进入模型上下文并影响工具行为，错误 Procedure、过拟合经验或恶意 Trace 的影响会被重复放大。人工审核确保适用范围、步骤、Pitfall、名称和更新目标合理，也保留用户对长期行为变化的最终控制权。
- 确认后的答案：一个 Completed Task 只能证明某一次执行成功，可能包含偶然路径、任务特例或未验证假设，不能证明方法稳定可复用。Vesta 因此先在多个 Completed Task 的轻量事实中识别重复模式，再只为候选 Cluster 读取真实 Trace，以成功 Task 更新为锚点提取工具调用、失败修正和验证证据；Distiller 根据多任务证据和现有 Skill 判断 CREATE、UPDATE 或 NONE。生成结果只是 Candidate，必须经 Human Gate 才能发布正式 Skill。这样把“做过一次”与“形成可靠经验”分开，并避免未经审核的经验持续影响后续 Agent 行为。
- 可能追问：
  - 为什么 Pattern Mining 阶段不直接读取所有 Trace？
  - Trace 缺失时为什么允许 Task-only fallback？
  - 如何避免同一批 Task 重试时重复创建 Candidate？
- 源码证据：
  - `backend/app/skill_learning/config.py`：batch、cluster、retry 和证据上限。
  - `backend/app/skill_learning/miner.py`：TaskCard Pattern Mining。
  - `backend/app/skill_learning/trace_selector.py`：Task Anchor 与相关 Step 区间。
  - `backend/app/skill_learning/evidence.py`：确定性结构化 Evidence。
  - `backend/app/skill_learning/service.py`：Watermark、Distillation、Candidate 与 Human Gate。

### Q10：Skill Learning 的 at-least-once 重试如何避免任务丢失和重复 Candidate？

- 状态：等待回答
- 你的原始回答：
- 确认后的答案：
- 可能追问：
- 源码证据：

## 面试前速记

后续从已经掌握的内容中提炼。
