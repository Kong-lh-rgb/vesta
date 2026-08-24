# Vesta Agent 综合评测与优化记录（2026-08-23）

## 结论

本轮把原本分散的 Core Agent、Memory 和 Skill Learning 评测统一到同一套结果、
成本和稳定性口径，并用真实 `deepseek-v4-flash` 完成了一轮 68 个稳定性单元、
每个重复 3 次的 Regression：共 204 个样本，通过 192 个，样本通过率 94.1%，
稳定场景通过率 83.8%，安全场景通过率 94.4%。

这不是“最终 100%”报告。完整 204 样本之后又修复了若干问题；由于用户要求停止
继续增加 API 开销，最后的 `eval-05` 和 `memory-03` 修复只完成了离线回归，尚未
再次 Live 验证。正式发布基线应在代码提交后再统一重跑。

## 一、评测框架

```text
YAML Scenario / Memory Phase
            ↓
真实领域 Harness（真实 AgentRuntime / Store / Context / Tools）
            ↓
确定性 Assertions 或 Learning Judge
            ↓
Adapter → EvalSampleRecord
            ↓
report.json + report.md + trace/sample 证据
            ↓
同场景重复运行 → 稳定通过率 → Baseline 门禁
```

统一的是结果，不是强迫三个领域使用同一种执行方式：

- Core：一次真实 `AgentRuntime.run()`，检查工具、Task、文件、答案与压缩事件；
- Memory：多个 Phase 共享 Memory Store，但按会话隔离聊天历史；
- Learning：真实运行 Mining → Evidence → Distillation → Candidate，由专项 Judge 判分；
- Computer、真实 MCP 和 macOS 审批继续留在 Integration / Manual E2E，不伪装成 CI 场景。

每条样本保存停止原因、Steps、工具调用、耗时和分层 Usage。Baseline 绑定 Provider、
Model、Suite、Tier、稳定性键和场景定义 SHA-256；题目变了就拒绝直接做升降比较。

## 二、实际优化过程

### 1. 第一次 Regression：先找到真实问题

[初始报告](../../backend/tests/eval_legacy/reports/comprehensive/20260823_091702_628798/report.md)
包含 68 个样本，57 个通过（83.8%），安全场景 83.3%，平均可计费 Token 3766。

失败并不都属于模型能力，逐条 Trace 后分为三类：

| 类型 | 实际案例 | 处理原则 |
| --- | --- | --- |
| 生产缺陷 | 文本 DSML 被当成答案、空 assistant 污染下一次请求、Prefix 越线不做摘要 | 修 Runtime 并补离线回归 |
| 模型策略波动 | Core 路由漏写、Skill CREATE/UPDATE 边界摇摆 | 加强策略并增加有界复核，不在 Harness 静默改结果 |
| Eval 缺陷 | 同义表达被逐字误判、Fixture 缺 Task Anchor、一个场景混测网络搜索 | 修断言/Fixture，保持生产规则不变 |

### 2. 生产层修复

- Runtime 对空 assistant 和文本工具协议各只做一次 request-only 修复；非法消息不会进入
  原始历史，连续失败会明确 `model_error`，不再伪造 `final_answer`。
- Prefix continuation 第一次越过压缩线时回到 canonical history，用真实历史边界生成滚动
  摘要；Active Skill 在压缩请求中继续保留。
- Host/Desktop 即使新会话历史为空，也会收到稳定的请求态默认系统提示；CLI 已持久化相同
  提示时去重，不写入数据库两次。
- Core 工具未暴露时，模型必须先 `tool_search` 再 `core_memory_update`；成功 ToolResult 前
  不能声称“已记住”。Reflection 禁止把漏写的 Core 偏好补成 Ordinary Memory。
- Skill Distiller 若在已有相关 Skill 时仍选择 CREATE，会做一次聚焦的 task-family overlap
  裁决；同族转 UPDATE，异族才保留 CREATE，原始裁决输出进入 Eval 证据。
- Provider 流在尚未交付任何可见文本/推理 delta 时中断，可按配置安全重试；一旦向 UI
  交付过内容就 fail-fast，避免重复输出。

### 3. Eval 层修复

- 保存 Pattern Mining、Distillation 以及 overlap adjudication 原始输出，能区分“未发现模式”
  与“发现模式但拒绝沉淀”。
- Memory 增加 `contains_any` 语义组；数字、否定、revision 等硬事实仍严格检查。
- Learning Fixture 使用真实 `task_id` Anchor、Agent Step、description/key facts，确保生产
  `TaskTraceSelector` 读到的证据与真实 Run 一致。
- `eval-27` 只禁止不存在的危险工具，不再把合法诊断工具也误判为失败。
- 语言、Task 策略、Skill 模板分别限制到被测工具集合，避免一道题同时测多个随机能力。
- CLI 每条样本立即刷新进度；报告检查预期样本数、重复 Run 编号和重复稳定性键，缺样本时
  禁止保存 Baseline。

## 三、结果与边界

[完整 3 次 Regression](../../backend/tests/eval_legacy/reports/comprehensive/20260823_112858_055392/report.md)：

| 指标 | 结果 |
| --- | --- |
| 场景稳定性单元 / 样本 | 68 / 204 |
| 样本通过 | 192 / 204（94.1%） |
| 稳定场景通过率 | 83.8% |
| 安全场景通过率 | 94.4% |
| 平均可计费 Token | 2767 |
| P95 可计费 Token | 7309 |
| 平均缓存命中率 | 75.5% |

随后对 11 个问题场景各跑 3 次，[诊断报告](../../backend/tests/eval_legacy/reports/comprehensive/20260823_125215_041071/report.md)
得到 25/33。它进一步暴露：

- `eval-05` 的 6K 测试窗口却预留 4096 输出 Token，摘要成功后仍没有输入预算；这是
  Fixture 数学错误，已改为合理输出预留并完成离线验证；
- `memory-03` 两次 Core 实际写入正确，仅因“先给出结论”未逐字匹配“先给结论”而失败；
  另一次是流在首个 delta 前断线，已分别修复语义断言和安全流重试；
- `learning-05a` 的 TaskCard 直接写“没有验证流程”，Miner 合理返回空簇，与场景想测试的
  Distiller 拒绝路径矛盾；修正证据层级后 [Live 复测 3/3](../../backend/tests/eval_legacy/reports/comprehensive/20260823_131617_888097/report.md)。

上述最后两项 Core/Context 修复没有继续 Live 重跑，因此不能宣称最终通过率 100%。此外，
初始报告和后续报告的场景摘要不同，83.8% → 94.1% 是工程演进轨迹，不是严格同题 A/B。

## 四、离线工程验证

- `pytest -q`：1004 passed；
- `ruff check .`：通过；
- `python -m compileall -q app tests`：通过；
- `git diff --check`：通过。

## 五、如何讲述这项工作

可以概括为：我没有用一个总准确率掩盖 Agent 的随机性，而是把 3 套已有领域 Harness 映射
到统一 Sample Record；用真实 Runtime、可解释断言、原始中间结果和每场景 3 次重复，分开
衡量质量、稳定性、安全和可计费成本。失败后先按 Trace 判断生产缺陷、模型波动还是 Eval
缺陷，再选择修 Runtime、增加有界模型复核或修正 Fixture，最后用离线回归和 Live Eval
分别验证确定性与语义能力。

下一次只需在代码提交后运行一次完整 Regression ×3，生成与单一 commit 绑定的新 Baseline；
不应在每次小改动后高成本全量调用真实模型。
