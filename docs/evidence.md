# Evidence：让上下文压缩可逆

## 解决的问题

Vesta 的数据库一直保存完整聊天历史，但模型请求必须受上下文预算约束。旧工具轮会被截短或移除，
旧对话会被滚动摘要替代。如果模型只有当前工作上下文，摘要遗漏的原始细节将无法自行找回。

Task 不能承担这个职责。Task 是会被模型持续更新的工作状态，适合保存目标、约束、步骤和进度；
工具原始输出属于不可变证据，二者的生命周期和一致性要求不同。

## 分层

```text
Conversation Store        完整原始聊天消息
        │
        ├── ContextManager        构建受预算控制的模型工作视图
        │     ├── 旧工具结果清理
        │     └── 旧对话滚动摘要
        │
ToolExecutor
        ├── 执行工具
        ├── EvidenceRecorder      在 20K 模型预览截断前保存原始输出
        └── ToolResult            有界预览 + evidence_id + SHA-256
                │
                ▼
SQLite Evidence Store     不可变原文，绑定 Conversation / Run / ToolCall
        │
        ├── evidence_search       按关键词定位证据
        └── evidence_read         按 ID 分页回读原文

Conversation Store
        ├── history_search        搜索当前会话原始消息
        └── history_read          按 sequence 读取消息窗口
```

## 关键规则

1. `ToolExecutor` 只依赖 `ToolOutputRecorder` 协议，不依赖 SQLite 或 Evidence 领域实现。
2. 工具输出先归档，再生成最多 20,000 字符的模型预览，因此截断不会破坏原文。
3. Evidence 以 `(run_id, tool_call_id)` 幂等创建；相同调用写入不同哈希时拒绝覆盖。
4. Evidence 与 History 工具必须从 `ToolExecutionContext` 获取 `conversation_id`，模型不能自行指定
   其它会话；跨会话证据表现为不存在。
5. 大证据按 `offset/limit` 分页读取，不自动重新注入完整原文。
6. 当前活动 Task 和唯一 `in_progress` Step 只作为 Evidence 元数据归因；记录证据不会修改 Task
   revision，也不会把不可变原文复制进可变任务文件。
7. 滚动摘要只保留重要 Evidence 的用途和完整 ID，不复制大段工具原文。
8. Normal 模式下回读工具采用延迟 Schema，由 `tool_search` 激活；Plan 模式可直接使用白名单内的
   只读 History/Evidence 工具。
9. Evidence 不再生成常驻模型上下文的全量索引。本轮工具结果直接携带稳定引用，历史证据则由
   `evidence_search/read` 按需发现，避免每个 Step 重复发送固定索引。
10. 是否归档由工具定义的 `record_output` 声明决定。执行类、读取类工具默认归档；Task、Memory、
    History、Evidence 等管理或回读工具显式关闭，避免硬编码名称判断和递归归档。
11. 单条原文默认最多 16 MiB，Evidence Store 默认总量最多 512 MiB。达到边界时拒绝新增证据、
    保留已有证据，工具原本的执行结果仍如实返回，并在 `ToolResult.evidence_error` 暴露归档失败。
12. 幂等检查、容量检查和写入位于同一个 `BEGIN IMMEDIATE` 事务中；Task/Step 归因属于可选元数据，
    归因失败不会阻止原始证据落盘。

## 一次流程示例

1. 模型调用 `read_file` 读取一个 80K 字符文件。
2. `EvidenceRecorder` 先把 80K 原文保存到 Evidence Store。
3. 模型收到 20K 有界预览，同时得到 `evidence_id`、原始字符数和 SHA-256。
4. 后续上下文整理可以压缩或移除旧工具轮，但不会删除 Evidence Store 的原文。
5. 模型需要被裁掉的中段时，先调用 `tool_search` 激活 `evidence_search/read`，再按关键词定位并
   分页读取相关区间。
6. 如果缺失的是旧对话里的用户约束，而不是工具输出，则使用 `history_search/read` 从 Conversation
   Store 读取原始消息。

## 当前边界

- 只对本次功能上线后的成功工具调用生成 Evidence，旧 Trace 中已经截断的输出无法反向恢复。
- Evidence 当前保存在本地 SQLite，已有硬容量边界，但尚未实现自动归档/清理、加密或 UI 浏览页面；
  容量不足时采用 fail closed，不会静默删除旧证据。
- 搜索使用 SQLite 确定性文本匹配，先保证可解释和离线可测；后续可在 Store 内部替换为 FTS，
  不改变 Agent 工具接口。
- Evidence 解决“原文可找回”，Task 解决“当前做到哪里”；它们互补，但不能相互替代。
