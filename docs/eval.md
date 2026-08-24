# Vesta Eval：从 73.3% 到可复现 Baseline

本文记录 2026-08-23 完成的第一轮 Vesta Agent 综合评测：为什么要评测、具体测了
什么、评测框架如何运行、最初暴露了哪些问题、生产代码和评测代码分别做了哪些
修改，以及指标如何一步步演进。

这不是一份只展示高分的报告。它同时保留失败样本、未完成的 Live 验证和不能直接
进行 A/B 比较的边界。

## 1. 最终结论

第一轮完整 Live Regression 覆盖 68 个稳定性单元，每个单元运行 3 次，共 204 个
样本：

| 指标 | 结果 |
| --- | ---: |
| 样本通过 | 192 / 204 |
| 样本通过率 | 94.1% |
| 稳定场景通过率 | 83.8% |
| 安全场景通过率 | 94.4% |
| 平均 Steps | 1.7 |
| 平均模型调用 | 2.2 |
| 平均可计费 Token | 2767 |
| P95 可计费 Token | 7309 |
| 平均缓存命中率 | 75.5% |
| 平均耗时 | 11.9 秒 |

完整报告位于：

- `backend/tests/eval/reports/comprehensive/20260823_112858_055392/report.md`
- Baseline：`backend/tests/eval/reports/baselines/deepseek-regression.json`

最终代码状态比这份 Baseline 略新：`eval-05` 和 `memory-03` 在完整 Regression 后又
做了修复，但为了控制真实 API 开销，只完成了离线验证，没有再次运行完整 Live Eval。
因此不能宣称最终通过率为 100%。

## 2. 为什么不能只看“回答对不对”

Agent 的一次输出由多层共同决定：

```text
用户请求
  ↓
上下文构建 / 系统提示 / 工具定义
  ↓
模型决策
  ↓
工具调用 / 审批 / 状态变更
  ↓
下一轮模型请求
  ↓
最终回答 / Post-Run
```

最终答案错误，原因可能是：

1. Runtime 状态机有缺陷；
2. 模型产生了概率性错误；
3. Provider 流式响应中断；
4. Fixture 没有满足生产领域契约；
5. Assertion 只匹配字面表达，造成假阴性；
6. 场景本身同时测试多个能力，归因不清楚。

因此 Vesta Eval 不只检查答案，还检查工具调用、停止原因、Task/Memory/Skill 的真实
落盘状态、上下文压缩事件、用量和中间模型输出。

## 3. 本轮覆盖的能力

### 3.1 Core Agent

- 简单问答和中文回答；
- 不需要工具时是否克制调用；
- 文件读取、写入和连续工具轮；
- 未注册工具、审批拒绝和危险操作；
- Task 创建、更新和会话隔离；
- Skill 发现、激活、资源读取和失败反馈；
- 上下文压缩后目标、摘要和 Active Skill 是否保留；
- 空 assistant、文本伪 Tool Call、模型错误和 Max Steps。

### 3.2 Memory

- Ordinary Memory 创建、召回和修改；
- Core Memory 路由；
- 跨会话召回；
- Revision 和真实存储状态；
- 容量上限及维护行为；
- Post-Run Reflection 的 `create`、`update`、`remove`、`none`。

### 3.3 Skill Learning

```text
Completed Tasks
      ↓
Pattern Mining
      ↓
Evidence Selection
      ↓
Distillation
      ↓
create / update / none
      ↓
Skill Candidate
```

评测覆盖无规律任务、重复任务、证据不足、已有 Skill 更新、Candidate 去重，以及
CREATE/UPDATE 边界。

Computer、真实外部 MCP 和 macOS 审批没有混入这套 CI 型评测。这些能力依赖真实设备
和外部服务，应由 Integration Test 或 Manual E2E 单独覆盖。

## 4. 评测框架如何工作

### 4.1 总体流程

```text
YAML Scenario / Memory Phase
            ↓
真实领域 Harness
            ↓
真实 AgentRuntime / Store / Context / Tools
            ↓
确定性 Assertions 或 Learning Judge
            ↓
Adapter → EvalSampleRecord
            ↓
report.json + report.md + Trace
            ↓
同场景重复运行
            ↓
稳定通过率与 Baseline 门禁
```

三套 Harness 保持各自真实语义：

- Core 使用真实 `AgentRuntime.run()`；
- Memory 通过多个 Phase 共享 Memory Store，同时隔离聊天会话；
- Learning 真实执行 Mining、Evidence、Distillation 和 Candidate 生成；
- Adapter 只统一输出结构，不篡改领域结果。

### 4.2 一个样本保存什么

统一的 `EvalSampleRecord` 至少保存：

- Suite、Scenario、Phase、Run 编号；
- Provider 和 Model；
- 是否通过以及每条 Check；
- Stop Reason、Steps、工具调用和工具失败；
- 耗时；
- Main Agent、Summary、Reflection 等分层 Usage；
- Trace 和临时运行现场；
- Learning 的 Mining、Distillation、Overlap 裁决原始输出。

### 4.3 如何判分

优先使用确定性事实：

- 是否调用了允许或禁止的工具；
- ToolResult 是否成功；
- 文件内容是否真实变化；
- Task 数量、状态、Owner 和 Steps；
- Memory revision、active count 和正文；
- Skill Candidate 的 action、name 和存储状态；
- Runtime 是否以预期 Stop Reason 结束。

只有无法用确定性事实表达的语义质量才交给专项 Judge。Judge 不能覆盖安全、状态机或
持久化事实。

同义断言允许表达变化，例如“先给结论”和“先给出结论”；数字上限、否定关系、
revision、Owner 和成功 ToolResult 仍必须严格。

### 4.4 稳定性如何计算

每个稳定性单元由以下键标识：

```text
(suite, scenario_id, phase_id, mode)
```

当 `--runs 3` 时，同一稳定性键必须包含 run 1、2、3，且三次全部通过，才算稳定通过。

因此：

- 样本通过率衡量所有单次运行；
- 稳定通过率衡量能力能否连续重复成功。

最终 192/204 表示只有 12 个失败样本；但这些失败分布在 11 个稳定性单元，所以只有
57/68 个单元实现 3/3，稳定通过率为 83.8%。

### 4.5 成本口径

V1 的“可计费 Token”近似为：

```text
uncached_input_tokens + output_tokens
```

如果 Provider 没有返回缓存明细，则保守地把全部 input tokens 计入。缓存输入在真实
Provider 中不一定完全免费，因此这个值用于工程比较和预算，不等同于最终账单金额。

### 4.6 Baseline 为什么需要 Digest

Baseline 会绑定：

- Provider / Model；
- Suites / Tier；
- Runs；
- 场景集合；
- Scenario Digest；
- Git Commit。

如果题目、Fixture 或断言发生变化，Digest 会变化，框架会拒绝把两份报告当成严格
A/B。这样可以防止通过修改题目制造虚假的“指标提升”。

## 5. 指标演进

### 5.1 初始 Smoke

第一轮只运行 15 个代表性样本：

| 指标 | 初始值 |
| --- | ---: |
| 样本通过 | 11 / 15 |
| 样本通过率 | 73.3% |
| 安全通过率 | 100% |
| 平均可计费 Token | 2483 |
| P95 Token | 7061 |
| 缓存命中率 | 58.4% |

主要失败：

- 一个整体任务被拆成多个 Task；
- 模型生成非法 Task priority；
- Memory 的合理同义表达被逐字断言误判；
- Learning Fixture 缺少 Task Trace Anchor 和具体证据；
- Skill CREATE/UPDATE 判断不稳定。

报告：`20260823_073914_431641/report.md`。

### 5.2 四条问题场景定向迭代

选择 Task、Memory Update、Learning CREATE 和 Learning UPDATE，每项运行 3 次：

| 迭代 | 通过 | 通过率 | 稳定通过率 |
| --- | ---: | ---: | ---: |
| 初次复现 | 4 / 12 | 33.3% | 0% |
| 第一批修改 | 5 / 12 | 41.7% | 25% |
| 第二批修改 | 10 / 12 | 83.3% | 50% |

分能力变化：

- Task：2/3 → 3/3；
- Memory Update：0/3 → 2/3；
- Learning CREATE/UPDATE：2/6 → 5/6。

这组低分不能代表整个系统，因为它只包含最初失败的四条问题场景。

### 5.3 Smoke 收口

15 个稳定性单元各运行 3 次，共 45 个样本：

| 指标 | 初始 Smoke | Smoke 收口 |
| --- | ---: | ---: |
| 样本通过率 | 73.3% | 95.6% |
| 稳定通过率 | — | 86.7% |
| 安全通过率 | 100% | 100% |
| 平均可计费 Token | 2483 | 1733 |
| P95 Token | 7061 | 3419 |
| 缓存命中率 | 58.4% | 81.6% |

工程趋势表现为通过率增加 22.3 个百分点、平均可计费 Token 下降约 30%、P95 下降
约 52%。由于场景定义经过修正，这仍是演进轨迹，而不是冻结题集的严格 A/B。

报告：`20260823_081807_566853/report.md`。

### 5.4 扩展 Regression

题集扩展到 68 个稳定性单元。第一次每项运行一次：

| 指标 | 结果 |
| --- | ---: |
| 样本通过 | 57 / 68 |
| 样本通过率 | 83.8% |
| 安全通过率 | 83.3% |
| 平均可计费 Token | 3766 |
| P95 Token | 8751 |
| 缓存命中率 | 68.0% |
| 平均 Steps | 1.9 |

分数低于 Smoke，主要因为加入了更难的 Skill、Context、Memory 路由、Provider 异常和
安全场景，不表示系统从 95.6% 退化到 83.8%。

报告：`20260823_091702_628798/report.md`。

### 5.5 Regression ×3

完成生产与 Eval 修复后，对 68 个稳定性单元各运行 3 次：

| 指标 | 扩展初始 | Regression ×3 | 工程变化 |
| --- | ---: | ---: | ---: |
| 样本通过率 | 83.8% | 94.1% | +10.3pp |
| 安全通过率 | 83.3% | 94.4% | +11.1pp |
| 平均 Steps | 1.9 | 1.7 | -10.5% |
| 平均模型调用 | 2.2 | 2.2 | 持平 |
| 平均可计费 Token | 3766 | 2767 | -26.5% |
| P95 Token | 8751 | 7309 | -16.5% |
| 缓存命中率 | 68.0% | 75.5% | +7.5pp |
| 平均耗时 | 11.3s | 11.9s | 未改善 |

两份报告的 Scenario Digest 不同，且一次是单次运行、一次是三次重复，所以表中是工程
演进趋势，不应包装成受控实验。

最终分组结果：

| 能力 | 通过率 |
| --- | ---: |
| Task | 100% |
| Tools | 100% |
| Memory | 97.0% |
| Context | 94.4% |
| Safety | 94.4% |
| Skill Runtime | 93.3% |
| Skill Learning | 88.9% |
| Basic | 88.9% |

## 6. 根据 Bad Case 做了什么修改

### 6.1 Runtime

- 空 assistant 不再进入原始历史，只允许一次 request-only 重试；
- 文本 DSML/伪 Tool Call 不再作为最终答案，也不会被执行；
- 连续协议错误明确返回 `model_error`，不伪造成功；
- Prefix continuation 越过压缩线时回退 canonical history 生成滚动摘要；
- 压缩请求继续保留 Active Skill；
- 默认系统提示在请求态稳定注入并去重；
- 工具轮上限和 Max Steps 使用真实停止原因。

### 6.2 Task

- 系统提示和 Schema 明确“一目标一 Task，子工作使用 Steps”；
- 只有相互独立的目标才允许创建多个 Task；
- 明确合法 priority，减少非法枚举值。

### 6.3 Memory

- Core 工具未暴露时先通过 `tool_search` 发现；
- Core 级偏好不能由 Reflection 降级写入 Ordinary Memory；
- 成功 ToolResult 前不能声称已经记住；
- Reflection 保存尝试次数、结束原因和原始输入输出；
- 同义表达使用语义候选组，数字、revision 和否定关系继续严格判断；
- 修复旧 Core 文档迁移。

### 6.4 Skill Learning

- 保存 Mining 和 Distillation 原始输出；
- Fixture 补齐 `task_id`、Agent Step、description、constraints 和 key facts；
- 已有相关 Skill 时增加一次聚焦的 Task Family Overlap 裁决；
- 同一任务族选择 UPDATE，不同任务族才 CREATE；
- Harness 不再静默修改模型 action。

### 6.5 Provider

- 流已经建立但尚未交付可见 delta 时，允许有界安全重试；
- 已经向 UI 输出过内容后立即失败，禁止重放造成重复文本；
- 失败尝试中的 Tool Delta 不进入最终结果。

### 6.6 Eval 本身

- Core、Memory、Learning 映射到统一 Sample Record；
- 检查预期样本数、Run 编号和稳定性键；
- Baseline 比较增加 Provider、Model、Suite、Tier 和 Digest 门禁；
- Safety 退化直接阻断，成本增加超过 20%只告警；
- 修复 Memory 字面断言、Learning Trace Anchor、未知危险工具断言；
- 混测场景限制允许的工具集合，降低无关随机性；
- 报告保存 Mining、Distillation 和 Overlap 裁决证据。

## 7. 最后一轮定向诊断

从完整 Regression 选择 11 个问题场景，各运行 3 次，共 33 个样本，结果为 25/33。
这不是全量成绩下降，而是只运行最难的失败集合。

- 8 个已修正场景达到 24/24；
- `eval-05` 为 1/3；
- `memory-03` 为 0/3；
- `learning-05a` 为 0/3。

归因结果：

1. `eval-05` 的测试窗口为 6000 Token，却预留 4096 输出和 100 margin，摘要完成后只剩
   1804 输入预算，属于 Fixture 数学错误；
2. `memory-03` 两次实际写入正确，仅因“先给出结论”没有逐字匹配“先给结论”；另一次
   是首个流 delta 前连接中断；
3. `learning-05a` 的 TaskCard 明确写着没有验证流程，Miner 合理返回空簇，与题目期待
   的 Distillation 拒绝路径冲突。

修正 `learning-05a` 后 Live 复测 3/3。`eval-05` 和 `memory-03` 的最后修复只做了离线
验证，没有继续消耗真实 API。

相关报告：

- `20260823_125215_041071/report.md`；
- `20260823_131617_888097/report.md`。

## 8. 如何运行

以下命令在 `backend/` 目录执行。

### 8.1 日常离线验证

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m compileall -q app tests
git diff --check
```

这些命令不应调用真实模型，适合每次提交和 CI。

### 8.2 定向 Live Eval

```bash
.venv/bin/python -m tests.eval.run_suite \
  --suite core \
  --scenario eval-05 \
  --runs 3 \
  --provider deepseek \
  --print \
  --allow-failures
```

修改某个模块后，只选择相关场景重复 3 次。

### 8.3 发布前完整 Regression

```bash
.venv/bin/python -m tests.eval.run_suite \
  --suite core \
  --suite memory \
  --suite learning \
  --tier regression \
  --runs 3 \
  --provider deepseek \
  --save-baseline tests/eval/reports/baselines/deepseek-regression.json \
  --print \
  --allow-failures
```

完整 Live Regression 成本较高，只应在里程碑、发布或模型切换前运行，不应在每次小改动
后执行。

## 9. 后续评测策略

```text
日常开发
  └─ 离线 pytest / Fake Model / 静态检查

模块发生重要修改
  └─ 相关问题样本 Live ×3

版本里程碑或发布
  └─ 完整 Regression ×3 + 新 Baseline
```

未来新增能力时分别建立专项边界：

- MCP：连接、工具发现、异常隔离和恶意 Server；
- Computer：真实 macOS E2E、目标恢复和输入结果验证；
- Automation：定时触发、恢复和重复执行保护；
- Desktop：RPC、流式输出和审批状态机集成测试。

## 10. 这次 Eval 最重要的经验

一次 Eval 失败必须先回答：

> 这是生产代码错了、模型不稳定、Provider 中断、Fixture 不真实，还是 Assertion 判错了？

只有完成归因，才决定修改 Runtime、增加有界模型复核，或者修正 Eval。本轮真正建立的
不是一张 94.1% 的成绩单，而是一套能够持续发现问题、保留证据、衡量稳定性，并且不会
为了过测试而扭曲生产架构的工程闭环。
